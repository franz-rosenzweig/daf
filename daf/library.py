"""Book identity: every Kindle copy, the audiobook and the vault note of one work
become one row in `books`, keyed by Calibre id when Calibre has it.

Matching is by normalized title (subtitles, articles and punctuation dropped),
checked against the author's surname when several books share a title.
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
    return t


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
    finally:
        c.close()
    return [{"id": r[0], "title": r[1], "path": str(db.parent / r[2]) if r[3] else None, "author": r[4] or ""} for r in rows]


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
        out.append({"title": fm.get("title") or p.stem, "author": fm.get("author", ""), "status": fm.get("status", ""),
                    "path": str(p.relative_to(config.VAULT))})
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
        self.cal = {}
        for b in cal:
            self.cal.setdefault(norm(b["title"]), []).append(b)
        self.vault = {}
        for v in vault:
            self.vault.setdefault(norm(v["title"]), []).append(v)

    @staticmethod
    def _pick(cands, author):
        if len(cands) == 1 or not author:
            return cands[0]
        s = surname(author)
        for c in cands:
            if s and s in c["author"].lower():
                return c
        return cands[0]

    def calibre(self, title, author):
        c = self.cal.get(norm(title))
        return self._pick(c, author) if c else None

    def vault_note(self, title, author):
        v = self.vault.get(norm(title))
        return self._pick(v, author) if v else None


def private_patterns(settings):
    return [p.lower() for p in settings.get("private_titles", [])]


def is_private(title, settings):
    t = (title or "").lower()
    return any(p in t for p in private_patterns(settings))


def rebuild(conn, settings):
    """Recompute books and book_keys from Calibre, the vault, the Kindle and Audiobookshelf."""
    cal, vault = calibre_books(), vault_books()
    m = Matcher(cal, vault)
    books, keys = {}, {}

    def ensure(bid, kind, title, author, cal_row=None):
        b = books.get(bid)
        if not b:
            b = books[bid] = {"id": bid, "kind": kind, "title": title, "author": author or None,
                              "calibre_id": cal_row["id"] if cal_row else None,
                              "calibre_path": cal_row["path"] if cal_row else None, "vault_path": None, "status": None,
                              "progress": None, "progress_note": None, "last_read": None, "audio_pct": None,
                              "audio_note": None, "url": None, "private": 0}
            v = m.vault_note(title, author)
            if v:
                b["vault_path"], b["status"] = v["path"], v["status"]
        return b

    def resolve(title, author):
        c = m.calibre(title, author)
        if c:
            return ensure(f"cal:{c['id']}", "book", c["title"], c["author"], c)
        v = m.vault_note(title, author)
        if v:
            slug = re.sub(r"[^a-z0-9]+", "-", norm(v["title"])).strip("-")
            return ensure(f"vault:{slug}", "book", v["title"], v["author"])
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
        if not m.calibre(v["title"], v["author"]):
            slug = re.sub(r"[^a-z0-9]+", "-", norm(v["title"])).strip("-")
            if not any(b.get("vault_path") == v["path"] for b in books.values()):
                ensure(f"vault:{slug}", "book", v["title"], v["author"])
        else:
            c = m.calibre(v["title"], v["author"])
            ensure(f"cal:{c['id']}", "book", c["title"], c["author"], c)

    # And every book in Calibre, so the whole library can be opened in Daf's reader.
    for c in cal:
        ensure(f"cal:{c['id']}", "book", c["title"], c["author"], c)

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

    conn.execute("DELETE FROM books WHERE kind = 'book'")
    conn.execute("DELETE FROM book_keys WHERE key NOT LIKE 'kk:%'")
    cols = ["id", "kind", "title", "author", "calibre_id", "calibre_path", "vault_path", "status", "progress",
            "progress_note", "last_read", "audio_pct", "audio_note", "url", "private"]
    conn.executemany(f"INSERT OR REPLACE INTO books ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     [tuple(b[c] for c in cols) for b in books.values()])
    conn.executemany("INSERT OR REPLACE INTO book_keys (key, book_id) VALUES (?, ?)", list(keys.items()))
    return len(books)


def add_paper_book(conn, title, author=None):
    """A book that exists only on paper: a vault note (so rebuild keeps it) and a books row."""
    from . import vaultnotes
    title, author = title.strip(), (author or "").strip() or None
    slug = re.sub(r"[^a-z0-9]+", "-", norm(title)).strip("-")
    if not slug:
        raise ValueError("A title, please")
    bid = f"vault:{slug}"
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
