"""Hardcover (hardcover.app), from Daf.

The vault already has a two-way Hardcover sync (`.claude/scripts/hardcover-sync.py`, every
30 minutes) that owns the book notes' `status`, `rating`, `read`, `consuming` and review, and
pushes `progress` (which koreader-merge.py writes from the Kindle). So Daf never writes those
frontmatter keys. It talks to Hardcover directly, and the vault sync then pulls the change
into the note (Hardcover changed, the vault didn't), the way it does for edits made on the site:

- progress from Daf's own book reader, only ever forward, never to a finished book;
- "Reading" when a book on the Want to read shelf is started in Daf;
- finished, with an optional rating, when Nathan says so (the book page, the end of a book
  in Daf, or Today when the Kindle reaches the end);
- a status or rating changed on a book page.

Daf reads his shelves for the Books page (Want to read) and book pages. Books are matched by
the `hardcoverBookId` in their vault note, or a link made in Daf (`hc_links`). Private books
are never sent on their own, and one added from Daf goes in private.
"""
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import date

from . import config, secrets

log = logging.getLogger(__name__)
API = "https://api.hardcover.app/v1/graphql"
STATUS = {1: "Want to read", 2: "Reading", 3: "Read", 4: "Paused", 5: "Did not finish"}
WRITE_DELAY = 1.1
FM_ID = re.compile(r"^hardcoverBookId:\s*['\"]?(\d+)", re.M)


def _today():
    """Today in his home time zone (the server's own clock may be in another)."""
    from . import today as T
    return T.today(config.load_settings()).isoformat()

QUERY = """{ me { id username user_books {
  id book_id status_id rating privacy_setting_id edition_id updated_at edition { pages }
  user_book_reads { id progress_pages started_at finished_at edition_id }
  book { title slug pages image { url } cached_contributors } } } }"""
UPDATE = "mutation($id:Int!,$o:UserBookUpdateInput!){update_user_book(id:$id,object:$o){id error}}"
INSERT = "mutation($o:UserBookCreateInput!){insert_user_book(object:$o){id error}}"
UPSERT_READ = ("mutation($ubid:Int!,$d:[DatesReadInput]!){upsert_user_book_reads(user_book_id:$ubid,datesRead:$d)"
               "{user_book_id error}}")
INSERT_READ = "mutation($ubid:Int!,$r:DatesReadInput!){insert_user_book_read(user_book_id:$ubid,user_book_read:$r){id error}}"


class HardcoverError(Exception):
    pass


def _key():
    k = (secrets.env().get("HARDCOVER_API_KEY") or "").strip()
    if not k:
        return None
    return k if k.lower().startswith("bearer ") else "Bearer " + k


def gql(query, variables=None):
    key = _key()
    if not key:
        raise HardcoverError("No Hardcover key (HARDCOVER_API_KEY in the vault's settings file; see docs/OPERATIONS.md)")
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json", "authorization": key,
                                          "User-Agent": "Daf (personal reading app)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise HardcoverError(f"Hardcover {e.code}") from e
    if d.get("errors"):
        raise HardcoverError(str(d["errors"])[:300])
    return d["data"]


def _check(d, field):
    err = (d.get(field) or {}).get("error")
    if err:
        raise HardcoverError(err)
    return d.get(field) or {}


# ---- his shelves, cached -----------------------------------------------------

def _kv(conn, k, default=None):
    r = conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
    return json.loads(r[0]) if r else default


def _kv_set(conn, k, v):
    conn.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (k, json.dumps(v)))


def fetch(conn, force=False, max_age=25 * 60):
    """{user, at, books: [user_book…]}; asks Hardcover at most every 25 minutes unless forced."""
    c = _kv(conn, "hardcover")
    if c and not force and time.time() - c["at"] < max_age:
        return c
    me = gql(QUERY)["me"][0]
    c = {"user": me["username"], "at": int(time.time()), "books": me["user_books"]}
    _kv_set(conn, "hardcover", c)
    return c


def by_hc(conn, **kw):
    return {ub["book_id"]: ub for ub in fetch(conn, **kw)["books"]}


# ---- which Daf book is which Hardcover book ------------------------------------

def build_map(conn):
    """Daf book id -> Hardcover book id, from the vault notes' hardcoverBookId and links made in Daf."""
    m = {}
    for bid, rel in conn.execute("SELECT id, vault_path FROM books WHERE vault_path IS NOT NULL AND kind = 'book'").fetchall():
        p = config.VAULT / rel
        try:
            with open(p, encoding="utf-8") as f:
                head = f.read(4000)
        except OSError:
            continue
        g = FM_ID.search(head.split("\n---", 1)[0] if head.startswith("---") else "")
        if g:
            m[bid] = int(g.group(1))
    for bid, hid in conn.execute("SELECT book_id, hc_book_id FROM hc_links"):
        m[bid] = hid
    _kv_set(conn, "hc_map", m)
    return m


def hc_map(conn):
    m = _kv(conn, "hc_map")
    return m if m is not None else build_map(conn)


def _pages(ub):
    return (ub.get("edition") or {}).get("pages") or (ub.get("book") or {}).get("pages")


def active_read(ub):
    """The read row that stands for where he is (the vault sync's rule, so the two agree)."""
    reads = [r for r in (ub.get("user_book_reads") or []) if r]
    if not reads:
        return None
    unfinished = [r for r in reads if not r.get("finished_at")]
    if unfinished:
        fu = max(unfinished, key=lambda r: r.get("progress_pages") or 0)
        fmax = max((r.get("progress_pages") or 0 for r in reads if r.get("finished_at")), default=0)
        if (fu.get("progress_pages") or 0) >= fmax:
            return fu
    pool = [r for r in reads if r.get("finished_at")] or unfinished
    return max(pool, key=lambda r: r.get("progress_pages") or 0) if pool else None


def _card(ub):
    b = ub.get("book") or {}
    r = active_read(ub) or {}
    pages = _pages(ub)
    authors = [c.get("author", {}).get("name") for c in (b.get("cached_contributors") or []) if c.get("author")]
    return {"ub_id": ub["id"], "hc_book_id": ub["book_id"], "status_id": ub["status_id"], "status": STATUS.get(ub["status_id"], "?"),
            "rating": ub.get("rating"), "title": b.get("title"), "author": ", ".join(a for a in authors[:2] if a),
            "slug": b.get("slug"), "image": (b.get("image") or {}).get("url"), "pages": pages,
            "progress_pages": r.get("progress_pages"), "finished_at": r.get("finished_at"), "private": ub.get("privacy_setting_id") == 3,
            "url": f"https://hardcover.app/books/{b.get('slug')}" if b.get("slug") else None}


def book_status(conn, book_id):
    """Hardcover's view of one Daf book, or {linked: False}."""
    hid = hc_map(conn).get(book_id)
    if not hid:
        return {"linked": False}
    ub = by_hc(conn).get(hid)
    if not ub:
        return {"linked": True, "hc_book_id": hid, "on_shelf": False}
    return {"linked": True, "on_shelf": True, **_card(ub)}


def shelf(conn, status_id=1):
    """A Hardcover shelf, each book matched to Daf's library where it can be."""
    rev = {}
    for bid, hid in hc_map(conn).items():
        rev.setdefault(hid, bid)
    from . import ebooks
    readable = ebooks.readable_ids(conn)
    out = []
    for ub in fetch(conn)["books"]:
        if ub["status_id"] != status_id:
            continue
        c = _card(ub)
        bid = rev.get(ub["book_id"])
        b = conn.execute("SELECT private, calibre_path FROM books WHERE id = ?", (bid,)).fetchone() if bid else None
        if b and b["private"]:
            continue
        c.update({"daf_id": bid, "readable": bool(bid and bid in readable), "has_cover": bool(b and b["calibre_path"])})
        out.append(c)
    out.sort(key=lambda c: (not c["readable"], (c["title"] or "").lower()))
    return out


# ---- writing to Hardcover ----------------------------------------------------------

def _ub_for(conn, book_id):
    hid = hc_map(conn).get(book_id)
    if not hid:
        raise HardcoverError("This book isn't linked to Hardcover yet")
    ub = by_hc(conn, force=True).get(hid)
    return hid, ub


def _fresh(conn, hid):
    return by_hc(conn, force=True).get(hid)


def set_status(conn, book_id, status_id=None, rating=None):
    hid, ub = _ub_for(conn, book_id)
    # Hardcover marks a book Read, dated today, the moment it's rated; so a rating only goes
    # with Read (here, or through finish()).
    if rating and (status_id or (ub or {}).get("status_id")) != 3:
        raise HardcoverError("Rate it once it's read: Hardcover marks a rated book Read")
    o = {}
    if status_id is not None:
        if status_id not in STATUS:
            raise HardcoverError("Unknown status")
        o["status_id"] = status_id
    if rating is not None:
        o["rating"] = max(0.5, min(5.0, round(float(rating) * 2) / 2)) if rating else None
    if not o:
        return book_status(conn, book_id)
    if not ub:
        priv = conn.execute("SELECT private FROM books WHERE id = ?", (book_id,)).fetchone()
        o.update({"book_id": hid, "status_id": o.get("status_id", 1), "privacy_setting_id": 3 if priv and priv[0] else 1})
        _check(gql(INSERT, {"o": o}), "insert_user_book")
    else:
        _check(gql(UPDATE, {"id": ub["id"], "o": o}), "update_user_book")
        if status_id == 2:
            ub = _fresh(conn, hid)     # Hardcover may have started a read itself
            if ub and not active_read(ub):
                _check(gql(INSERT_READ, {"ubid": ub["id"], "r": {"started_at": _today(), "edition_id": ub.get("edition_id")}}),
                       "insert_user_book_read")
    fetch(conn, force=True)
    return book_status(conn, book_id)


def finish(conn, book_id, rating=None, day=None):
    """Read, with the date (today unless given) on the read and the progress at the last page."""
    hid, ub = _ub_for(conn, book_id)
    if not ub:
        set_status(conn, book_id, 3, rating)
        hid, ub = _ub_for(conn, book_id)
    day = day or _today()
    o = {"status_id": 3}
    if rating:
        o["rating"] = max(0.5, min(5.0, round(float(rating) * 2) / 2))
    _check(gql(UPDATE, {"id": ub["id"], "o": o}), "update_user_book")
    # Marking it Read can make Hardcover write a finished read of its own, dated today: look again,
    # then date the read that stands for this one instead of adding another.
    ub = _fresh(conn, hid) or ub
    r = active_read(ub)
    pages = _pages(ub)
    d = {"finished_at": day, "edition_id": (r or {}).get("edition_id") or ub.get("edition_id")}
    if pages:
        d["progress_pages"] = pages
    if r and (not r.get("finished_at") or r["finished_at"][:10] != day):
        d["id"] = r["id"]
        _check(gql(UPSERT_READ, {"ubid": ub["id"], "d": [d]}), "upsert_user_book_reads")
    elif not r:
        d["started_at"] = day
        _check(gql(INSERT_READ, {"ubid": ub["id"], "r": d}), "insert_user_book_read")
    fetch(conn, force=True)
    return book_status(conn, book_id)


def link(conn, book_id, hc_book_id):
    conn.execute("INSERT INTO hc_links (book_id, hc_book_id, linked) VALUES (?, ?, ?) ON CONFLICT(book_id) DO UPDATE SET "
                 "hc_book_id = excluded.hc_book_id, linked = excluded.linked", (book_id, int(hc_book_id), int(time.time())))
    build_map(conn)


def search(conn, book_id=None, q=None):
    """Candidates on Hardcover: the Calibre ISBN first, then title and author."""
    hits = []
    if book_id and not q:
        b = conn.execute("SELECT title, author, calibre_id FROM books WHERE id = ?", (book_id,)).fetchone()
        if not b:
            return []
        if b["calibre_id"]:
            from .db import read_only
            c = read_only(config.CALIBRE_DBS[0])
            try:
                isbns = [r[0] for r in c.execute("SELECT val FROM identifiers WHERE book = ? AND type IN ('isbn', 'isbn13', 'isbn10')", (b["calibre_id"],))]
            finally:
                c.close()
            for isbn in isbns[:2]:
                isbn = re.sub(r"[^0-9Xx]", "", isbn)
                f = "isbn_13" if len(isbn) == 13 else "isbn_10"
                for e in gql("query($i:String!){ editions(where:{%s:{_eq:$i}}, limit:1){ book { id title slug image { url } cached_contributors release_year } } }" % f,
                             {"i": isbn})["editions"]:
                    bk = e["book"]
                    hits.append({"id": bk["id"], "title": bk["title"], "year": bk.get("release_year"), "image": (bk.get("image") or {}).get("url"),
                                 "author": ", ".join(c["author"]["name"] for c in (bk.get("cached_contributors") or [])[:2] if c.get("author")), "isbn": True})
        q = f"{b['title'].split(':')[0]} {b['author'] or ''}".strip()
    if q:
        res = gql('query($q:String!){ search(query:$q, query_type:"Book", per_page:6, page:1){ results } }', {"q": q})["search"]["results"]
        for h in (res or {}).get("hits", []):
            d = h["document"]
            if any(x["id"] == int(d["id"]) for x in hits):
                continue
            hits.append({"id": int(d["id"]), "title": d.get("title"), "year": d.get("release_year"), "image": (d.get("image") or {}).get("url"),
                         "author": ", ".join((d.get("author_names") or [])[:2]), "readers": d.get("users_count")})
    return hits[:8]


# ---- on its own, every half hour -------------------------------------------------

def push_progress(conn, settings, max_writes=5):
    """Progress from Daf's book reader, forward only. Starts a Want-to-read book as Reading."""
    if not settings.get("hc_progress", True) or not _key():
        return []
    done = _kv(conn, "hc_pushed", {})
    m, ubs = hc_map(conn), None
    out, writes = [], 0
    for r in conn.execute("SELECT p.book_id, p.fraction, p.updated, b.private FROM book_positions p JOIN books b ON b.id = p.book_id "
                          "WHERE p.fraction >= 0.02").fetchall():
        if r["private"] or r["book_id"] not in m or done.get(r["book_id"]) == round(r["fraction"], 3):
            continue
        if writes >= max_writes:
            break
        ubs = ubs or by_hc(conn, force=True)
        ub = ubs.get(m[r["book_id"]])
        done[r["book_id"]] = round(r["fraction"], 3)
        if not ub or ub["status_id"] in (3, 5):
            continue
        pages = _pages(ub)
        try:
            if ub["status_id"] == 1 and settings.get("hc_autostart", True):
                _check(gql(UPDATE, {"id": ub["id"], "o": {"status_id": 2}}), "update_user_book")
                writes += 1
                out.append({"book_id": r["book_id"], "did": "Reading"})
                time.sleep(WRITE_DELAY)
                ub = _fresh(conn, m[r["book_id"]]) or ub   # it may have started a read itself
            if not pages:
                continue
            want, rd = round(r["fraction"] * pages), active_read(ub)
            if rd and rd.get("finished_at"):
                continue
            if want > ((rd or {}).get("progress_pages") or 0):
                d = {"progress_pages": want, "edition_id": (rd or {}).get("edition_id") or ub.get("edition_id")}
                if rd:
                    d["id"] = rd["id"]
                    _check(gql(UPSERT_READ, {"ubid": ub["id"], "d": [d]}), "upsert_user_book_reads")
                else:
                    d["started_at"] = _today()
                    _check(gql(INSERT_READ, {"ubid": ub["id"], "r": d}), "insert_user_book_read")
                writes += 1
                out.append({"book_id": r["book_id"], "did": f"p. {want} of {pages}"})
                time.sleep(WRITE_DELAY)
        except HardcoverError as e:
            log.warning("hardcover push %s: %s", r["book_id"], e)
            out.append({"book_id": r["book_id"], "did": "failed", "error": str(e)})
    _kv_set(conn, "hc_pushed", done)
    if writes:
        fetch(conn, force=True)
    if out:
        _kv_set(conn, "hc_last", {"at": int(time.time()), "items": out})
    return out


def finished_on_kindle(conn, settings):
    """Books the Kindle has read to the end (98%+) that Hardcover doesn't call Read yet; for a nudge on Today."""
    if not _key():
        return []
    m = hc_map(conn)
    ubs = by_hc(conn)
    asked = set(_kv(conn, "hc_finish_asked", []))
    out = []
    for b in conn.execute("SELECT id, title, author, progress, last_read FROM books WHERE kind = 'book' AND private = 0 AND progress >= 98 "
                          "AND last_read > ? ORDER BY last_read DESC", (int(time.time()) - 21 * 86400,)):
        hid = m.get(b["id"])
        ub = ubs.get(hid) if hid else None
        if not ub or ub["status_id"] == 3 or b["id"] in asked:
            continue
        out.append({"id": b["id"], "title": b["title"], "author": b["author"]})
    return out[:2]


def dismiss_finish(conn, book_id):
    asked = _kv(conn, "hc_finish_asked", [])
    if book_id not in asked:
        asked.append(book_id)
        _kv_set(conn, "hc_finish_asked", asked[-200:])


# ---- his Hardcover lists, as Daf shelves -------------------------------------------
# Each list he made on Hardcover is a shelf in Daf (shelves.hc_list), kept the same both ways:
# the half-hourly sync brings Hardcover's list into the shelf, and a book put on or taken off the
# shelf in Daf goes to Hardcover at once. Only books Daf knows on Hardcover (hc_map) take part;
# a private book never goes up, and the rest of a list is left alone. A shelf made in Daf stays
# in Daf: lists can be public, so Daf never makes one.

LISTS = "{ me { username lists { id name slug list_books { id book_id } } } }"


def sync_lists(conn):
    """Bring every Hardcover list into its shelf. Returns how many lists."""
    me = gql(LISTS)["me"][0]
    to_daf = {}
    for bid, hid in hc_map(conn).items():
        to_daf.setdefault(int(hid), bid)
    now, seen, cache = int(time.time()), [], {}
    for lst in me["lists"]:
        lid = int(lst["id"])
        seen.append(lid)
        cache[str(lid)] = {"slug": lst["slug"], "books": {str(b["book_id"]): b["id"] for b in lst["list_books"]}}
        row = conn.execute("SELECT id FROM shelves WHERE hc_list = ?", (lid,)).fetchone()
        if row:
            sid = row[0]
            conn.execute("UPDATE shelves SET name = ? WHERE id = ?", (lst["name"], sid))
        else:
            sid = f"hc-{lid}"
            conn.execute("INSERT OR REPLACE INTO shelves (id, name, created, hc_list) VALUES (?, ?, ?, ?)", (sid, lst["name"], now, lid))
        want = {to_daf[b["book_id"]] for b in lst["list_books"] if b["book_id"] in to_daf}
        have = {r[0] for r in conn.execute("SELECT book_id FROM shelf_books WHERE shelf_id = ?", (sid,))}
        conn.executemany("INSERT OR IGNORE INTO shelf_books (shelf_id, book_id, added) VALUES (?, ?, ?)", [(sid, b, now) for b in want - have])
        conn.executemany("DELETE FROM shelf_books WHERE shelf_id = ? AND book_id = ?", [(sid, b) for b in have - want])
    # A list deleted on Hardcover leaves its shelf in Daf, as an ordinary shelf.
    conn.execute(f"UPDATE shelves SET hc_list = NULL WHERE hc_list IS NOT NULL AND hc_list NOT IN ({','.join('?' * len(seen))})", seen)
    _kv_set(conn, "hc_lists", {"user": me["username"], "lists": cache})
    return len(seen)


def list_url(conn, list_id):
    c = _kv(conn, "hc_lists") or {}
    lst = (c.get("lists") or {}).get(str(list_id))
    return f"https://hardcover.app/@{c['user']}/lists/{lst['slug']}" if lst and c.get("user") else None


def _linked(conn, shelf_id):
    r = conn.execute("SELECT hc_list FROM shelves WHERE id = ?", (shelf_id,)).fetchone()
    return int(r[0]) if r and r[0] else None


def list_add(conn, shelf_id, book_id):
    """The book onto the Hardcover list behind this shelf, if there is one."""
    lid = _linked(conn, shelf_id)
    if not lid:
        return None
    b = conn.execute("SELECT private FROM books WHERE id = ?", (book_id,)).fetchone()
    if b and b["private"]:
        raise HardcoverError("This shelf is a Hardcover list, and private books stay off Hardcover")
    hid = hc_map(conn).get(book_id)
    if not hid:
        raise HardcoverError("Hardcover doesn’t know this book yet. On its page, under Hardcover, choose “Find it on Hardcover”, then add it")
    c = _kv(conn, "hc_lists") or {"lists": {}}
    books = c.setdefault("lists", {}).setdefault(str(lid), {"slug": "", "books": {}})["books"]
    if str(hid) in books:
        return books[str(hid)]
    d = gql("mutation($o:ListBookInput!){insert_list_book(object:$o){id}}", {"o": {"list_id": lid, "book_id": int(hid)}})
    lbid = (d.get("insert_list_book") or {}).get("id")
    if not lbid:
        raise HardcoverError("Hardcover didn't add it to the list")
    books[str(hid)] = lbid
    _kv_set(conn, "hc_lists", c)
    return lbid


def list_remove(conn, shelf_id, book_id):
    """The book off the Hardcover list behind this shelf, if there is one."""
    lid = _linked(conn, shelf_id)
    hid = hc_map(conn).get(book_id) if lid else None
    if not hid:
        return None
    c = _kv(conn, "hc_lists") or {"lists": {}}
    books = ((c.get("lists") or {}).get(str(lid)) or {}).get("books") or {}
    if str(hid) not in books:                       # added on Hardcover since the last sync: look again
        sync_lists(conn)
        c = _kv(conn, "hc_lists") or {"lists": {}}
        books = ((c.get("lists") or {}).get(str(lid)) or {}).get("books") or {}
    lbid = books.get(str(hid))
    if not lbid:
        return None
    gql("mutation($id:Int!){delete_list_book(id:$id){id}}", {"id": int(lbid)})
    books.pop(str(hid), None)
    _kv_set(conn, "hc_lists", c)
    return lbid


def list_rename(conn, shelf_id, name):
    lid = _linked(conn, shelf_id)
    if lid:
        gql("mutation($id:Int!,$o:ListInput!){update_list(id:$id,object:$o){id}}", {"id": lid, "o": {"name": name}})

