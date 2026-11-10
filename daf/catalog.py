"""The library as a spreadsheet (#catalog, "All books"): every Calibre book with its Calibre fields
(custom columns too) and what Daf knows about it (status from the vault note, progress, last read,
highlights, shelves), searched the way Calibre searches, sorted by any column, saved as views and
exported as CSV. Calibre's metadata.db is only read here.

Search (Calibre's syntax, mostly):
  words                 every word somewhere in the title, authors, series, tags, publisher, shelves…
  tags:fic              contains   tags:"=Fiction" exact   tags:~^hist regex   tags:false none at all
  rating:>3  pages:<200  size:>5mb  highlights:>0  progress:>=50
  added:>30daysago  added:thismonth  published:<1950  modified:2026-11  (today, yesterday, thisweek,
  thismonth, thisyear, lastmonth, lastyear, Ndaysago, YYYY, YYYY-MM, YYYY-MM-DD; date: = added:)
  formats:false (no file)  cover:false  #read:=Finished  #pages:>300
  and, or, not, (…)     "-" before a field term is not too
"""
import csv
import html
import io
import re
import unicodedata
from datetime import date, datetime, timedelta

from . import config
from .db import read_only

# key, label, type, Calibre's own name for the field (search aliases)
BUILTIN = [
    ("title", "Title", "text", ()),
    ("authors", "Author", "list", ("author",)),
    ("series", "Series", "text", ()),
    ("tags", "Tags", "list", ("tag",)),
    ("rating", "Rating", "rating", ()),
    ("added", "Added", "date", ("date", "timestamp")),
    ("published", "Published", "date", ("pubdate",)),
    ("modified", "Modified", "date", ("last_modified",)),
    ("publisher", "Publisher", "text", ()),
    ("languages", "Language", "list", ("language", "lang")),
    ("formats", "Formats", "list", ("format",)),
    ("size", "Size", "size", ()),
    ("isbn", "ISBN", "text", ()),
    ("identifiers", "Identifiers", "list", ("identifier", "id_")),
    ("cover", "Cover", "bool", ()),
    ("status", "Status", "text", ()),
    ("progress", "Progress", "percent", ("kindle",)),
    ("last_read", "Last read", "date", ("read_date", "lastread")),
    ("audio", "Audiobook", "percent", ()),
    ("highlights", "Highlights", "number", ()),
    ("shelves", "Shelves", "list", ("shelf",)),
    ("calibre_id", "Calibre ID", "number", ("id",)),
]
DEFAULT_COLS = ["title", "authors", "series", "tags", "rating", "added", "formats", "#pages", "status", "progress"]
STATUS = {"to-read": "To read", "reading": "Reading", "read": "Read", "paused": "Paused", "dropped": "Dropped"}
TEXTISH = ("title", "authors", "series", "tags", "publisher", "shelves", "status", "formats", "isbn")


def fold(s):
    """Text to compare: lower case, without accents or Hebrew points."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(ch)).casefold()


def _tz(settings):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(settings.get("home_tz") or "America/Phoenix")
    except Exception:  # noqa: BLE001
        return None


def _day(ts, tz):
    """Calibre's 'YYYY-MM-DD HH:MM:SS(.ffffff)+00:00' → the date at home, 'YYYY-MM-DD'. Calibre's empty
    date (year 101) → None."""
    if not ts or str(ts).startswith("0101") or str(ts).startswith("0100"):
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace(" ", "T"))
        if d.tzinfo and tz:
            d = d.astimezone(tz)
        return d.date().isoformat()
    except ValueError:
        return str(ts)[:10]


# ---------- reading the library ----------
_cache = {"key": None, "books": None, "custom": None}


def _custom_columns(c):
    out = []
    import json as _json
    for cid, label, name, dtype, multi, normalized, display in c.execute(
            "SELECT id, label, name, datatype, is_multiple, normalized, display FROM custom_columns WHERE mark_for_delete = 0 ORDER BY id"):
        if dtype in ("composite",):
            continue
        try:
            enum = (_json.loads(display or "{}") or {}).get("enum_values") or None
        except ValueError:
            enum = None
        typ = {"int": "number", "float": "number", "bool": "bool", "rating": "rating", "datetime": "date"}.get(dtype, "list" if multi else "text")
        if re.fullmatch(r"\W*", name or ""):
            name = "#" + label
        out.append({"id": cid, "key": "#" + label, "label": name, "type": typ, "dtype": dtype, "multi": bool(multi), "normalized": bool(normalized), "enum": enum})
    return out


def calibre_rows(settings=None):
    """Every book in Calibre, as {calibre_id: {field: value}}, kept until metadata.db changes."""
    db = config.CALIBRE_DBS[0]
    try:
        st = db.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}, []
    if _cache["key"] == key:
        return _cache["books"], _cache["custom"]
    tz = _tz(settings or config.load_settings())
    c = read_only(db)
    try:
        books = {}
        for bid, title, tsort, ts, pub, sidx, asort, has_cover, mod, path in c.execute(
                "SELECT id, title, sort, timestamp, pubdate, series_index, author_sort, has_cover, last_modified, path FROM books"):
            try:                                     # the cover's own time: its address changes with it
                cover_v = int((db.parent / path / "cover.jpg").stat().st_mtime) if has_cover else 0
            except OSError:
                cover_v = 0
            books[bid] = {"calibre_id": bid, "title": title, "title_sort": tsort or title, "author_sort": asort or "", "cover_v": cover_v,
                          "added": _day(ts, tz), "published": _day(pub, tz), "modified": _day(mod, tz), "series_index": sidx,
                          "cover": bool(has_cover), "authors": [], "tags": [], "languages": [], "formats": [], "identifiers": [],
                          "series": None, "series_sort": None, "publisher": None, "rating": None, "size": None, "isbn": None}
        for b, name in c.execute("SELECT l.book, a.name FROM books_authors_link l JOIN authors a ON a.id = l.author ORDER BY l.id"):
            if b in books:
                books[b]["authors"].append((name or "").replace("|", ","))     # Calibre keeps an author's comma as |
        for b, name in c.execute("SELECT l.book, t.name FROM books_tags_link l JOIN tags t ON t.id = l.tag ORDER BY t.name COLLATE NOCASE"):
            if b in books:
                books[b]["tags"].append(name)
        for b, name, ssort in c.execute("SELECT l.book, s.name, s.sort FROM books_series_link l JOIN series s ON s.id = l.series"):
            if b in books:
                books[b]["series"], books[b]["series_sort"] = name, ssort or name
        for b, name in c.execute("SELECT l.book, p.name FROM books_publishers_link l JOIN publishers p ON p.id = l.publisher"):
            if b in books:
                books[b]["publisher"] = name
        for b, r in c.execute("SELECT l.book, r.rating FROM books_ratings_link l JOIN ratings r ON r.id = l.rating"):
            if b in books and r:
                books[b]["rating"] = r / 2
        for b, code in c.execute("SELECT l.book, g.lang_code FROM books_languages_link l JOIN languages g ON g.id = l.lang_code ORDER BY l.item_order"):
            if b in books:
                books[b]["languages"].append(code)
        for b, fmt, size in c.execute("SELECT book, format, uncompressed_size FROM data ORDER BY format"):
            if b in books:
                books[b]["formats"].append(fmt.upper())
                books[b]["size"] = max(books[b]["size"] or 0, size or 0) or None
        for b, typ, val in c.execute("SELECT book, type, val FROM identifiers ORDER BY type"):
            if b in books:
                books[b]["identifiers"].append(f"{typ}:{val}")
                if typ in ("isbn", "isbn13", "isbn10") and not books[b]["isbn"]:
                    books[b]["isbn"] = re.sub(r"[^0-9Xx]", "", str(val))
        custom = _custom_columns(c)
        for col in custom:
            n, k = col["id"], col["key"]
            for b in books.values():
                b[k] = [] if col["type"] == "list" else None
            if col["normalized"]:
                q = f"SELECT l.book, v.value FROM books_custom_column_{n}_link l JOIN custom_column_{n} v ON v.id = l.value ORDER BY l.id"
            else:
                q = f"SELECT book, value FROM custom_column_{n}"
            try:
                rows = c.execute(q).fetchall()
            except Exception:  # noqa: BLE001 - a column Calibre half-made
                continue
            for b, v in rows:
                if b not in books or v is None:
                    continue
                if col["dtype"] == "rating":
                    v = v / 2
                elif col["dtype"] == "datetime":
                    v = _day(v, tz)
                elif col["dtype"] == "bool":
                    v = bool(v)
                elif col["dtype"] == "comments":
                    v = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(v)))).strip()
                if col["type"] == "list":
                    books[b][k].append(v)
                else:
                    books[b][k] = v
    finally:
        c.close()
    _cache.update(key=key, books=books, custom=custom)
    return books, custom


def columns(custom):
    out = [{"key": k, "label": l, "type": t} for k, l, t, _ in BUILTIN]
    out += [{"key": c["key"], "label": c["label"], "type": c["type"], "custom": True, "dtype": c.get("dtype"), "multi": c.get("multi", False), "enum": c.get("enum")} for c in custom]
    return out


def rows(conn, settings=None, private=False):
    """Every Calibre book with Daf's side joined in: [{id, …fields}]."""
    settings = settings or config.load_settings()
    cal, custom = calibre_rows(settings)
    tz = _tz(settings)
    daf = {r["calibre_id"]: dict(r) for r in conn.execute(
        "SELECT id, calibre_id, status, progress, progress_note, last_read, audio_pct, private FROM books WHERE calibre_id IS NOT NULL")}
    hl = {r[0]: r[1] for r in conn.execute("SELECT book_id, COUNT(*) FROM highlights WHERE deleted = 0 GROUP BY book_id")}
    shelves = {}
    for bid, name in conn.execute("SELECT sb.book_id, s.name FROM shelf_books sb JOIN shelves s ON s.id = sb.shelf_id ORDER BY s.name"):
        shelves.setdefault(bid, []).append(name)
    out = []
    for cid, b in cal.items():
        d = daf.get(cid) or {}
        if d.get("private") and not private:
            continue
        bid = d.get("id") or f"cal:{cid}"
        lr = d.get("last_read")
        out.append(b | {
            "id": bid, "private": bool(d.get("private")),
            "status": STATUS.get(d.get("status"), (d.get("status") or "").capitalize() or None),
            "progress": d.get("progress"), "progress_note": d.get("progress_note"),
            "last_read": datetime.fromtimestamp(lr, tz).date().isoformat() if lr else None,
            "audio": d.get("audio_pct"), "highlights": hl.get(bid, 0), "shelves": shelves.get(bid, []),
        })
    return out, columns(custom)


# ---------- search ----------
class SearchError(ValueError):
    pass


def _tokens(q):
    toks, i, n = [], 0, len(q)
    while i < n:
        ch = q[i]
        if ch.isspace():
            i += 1
        elif ch in "()":
            toks.append(ch)
            i += 1
        elif ch == '"':
            j = q.find('"', i + 1)
            j = n if j < 0 else j
            toks.append(("word", q[i + 1:j], True))
            i = j + 1
        else:
            j, buf = i, ""
            while j < n and not q[j].isspace() and q[j] not in "()":
                if q[j] == '"':                       # field:"a quoted value"
                    k = q.find('"', j + 1)
                    k = n if k < 0 else k
                    buf += q[j + 1:k]
                    j = k + 1
                    continue
                buf += q[j]
                j += 1
            low = buf.lower()
            toks.append(low if low in ("and", "or", "not") else ("word", buf, False))
            i = j
    return toks


def _fields(cols):
    f = {}
    for k, label, typ, aliases in BUILTIN:
        f[k] = (k, typ)
        for a in aliases:
            f[a] = (k, typ)
    for c in cols:
        if c.get("custom"):
            f[c["key"].lower()] = (c["key"], c["type"])
            f.setdefault(c["key"][1:].lower(), (c["key"], c["type"]))
    f["file"] = ("formats", "list")
    return f


def parse(q, cols):
    """The search → a function book → bool."""
    toks, fields = _tokens(q or ""), _fields(cols)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        pos[0] += 1
        return toks[pos[0] - 1]

    def or_():
        left = and_()
        while peek() == "or":
            take()
            right = and_()
            left = (lambda a, b: lambda x: a(x) or b(x))(left, right)
        return left

    def and_():
        left = not_()
        while peek() is not None and peek() not in ("or", ")"):
            if peek() == "and":
                take()
                if peek() is None:
                    break
            right = not_()
            left = (lambda a, b: lambda x: a(x) and b(x))(left, right)
        return left

    def not_():
        if peek() == "not":
            take()
            if peek() is None:
                return lambda x: True
            inner = not_()
            return lambda x: not inner(x)
        return atom()

    def atom():
        t = take()
        if t == "(":
            if peek() in (None, ")"):
                if peek() == ")":
                    take()
                return lambda x: True
            e = or_()
            if peek() == ")":
                take()
            return e
        if t == ")":                                  # a stray one: nothing to do
            return lambda x: True
        if t in ("and", "or"):
            return lambda x: True
        _, text, quoted = t
        if not quoted:
            m = re.match(r"^(-?)(#?[A-Za-z_][\w]*):(.*)$", text, re.S)
            if m and m.group(2).lower() in fields:
                key, typ = fields[m.group(2).lower()]
                f = term(key, typ, m.group(3))
                return (lambda g: lambda x: not g(x))(f) if m.group(1) else f
        return plain(text)

    e = or_() if toks else (lambda x: True)
    return e


def plain(text):
    w = fold(text)
    if not w:
        return lambda x: True

    def f(x):
        hay = x.get("_hay")
        if hay is None:
            parts = [x.get("title"), x.get("series"), x.get("publisher"), x.get("status"), x.get("isbn")]
            parts += x.get("authors", []) + x.get("tags", []) + x.get("shelves", []) + x.get("formats", [])
            parts += [v for k, v in x.items() if k.startswith("#") and isinstance(v, str)]
            parts += [i for k, v in x.items() if k.startswith("#") and isinstance(v, list) for i in v if isinstance(i, str)]
            hay = x["_hay"] = fold(" ".join(p for p in parts if p))
        return w in hay
    return f


OPS = (">=", "<=", "!=", ">", "<", "=")


def _op(v):
    for o in OPS:
        if v.startswith(o):
            return o, v[len(o):].strip()
    return None, v.strip()


def _period(v, today=None):
    """A date search value → [start, end) dates."""
    today = today or date.today()
    s = v.strip().lower().replace(" ", "")
    if s == "today":
        return today, today + timedelta(1)
    if s == "yesterday":
        return today - timedelta(1), today
    if s == "thisweek":                                # the week starts on Sunday
        start = today - timedelta((today.weekday() + 1) % 7)
        return start, start + timedelta(7)
    if s == "thismonth":
        start = today.replace(day=1)
        return start, (start + timedelta(32)).replace(day=1)
    if s == "lastmonth":
        end = today.replace(day=1)
        return (end - timedelta(1)).replace(day=1), end
    if s == "thisyear":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1)
    if s == "lastyear":
        return date(today.year - 1, 1, 1), date(today.year, 1, 1)
    m = re.fullmatch(r"(\d+)(days?|weeks?|months?|years?)ago", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)[0]
        days = n * {"d": 1, "w": 7, "m": 30, "y": 365}[unit]
        d = today - timedelta(days)
        return d, d + timedelta(1)
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", s)
    if m:
        y, mo, d = int(m.group(1)), m.group(2), m.group(3)
        if d:
            start = date(y, int(mo), int(d))
            return start, start + timedelta(1)
        if mo:
            start = date(y, int(mo), 1)
            return start, (start + timedelta(32)).replace(day=1)
        return date(y, 1, 1), date(y + 1, 1, 1)
    raise SearchError(f"“{v}” isn't a date")


def _size(v):
    m = re.fullmatch(r"([\d.]+)\s*(kb|k|mb|m|gb|g|b)?", v.strip().lower())
    if not m:
        raise SearchError(f"“{v}” isn't a size")
    mult = {"b": 1, "k": 1024, "kb": 1024, "m": 1024 ** 2, "mb": 1024 ** 2, "g": 1024 ** 3, "gb": 1024 ** 3, None: 1024 ** 2}[m.group(2)]
    return float(m.group(1)) * mult


def _cmp(o, a, b):
    return {"=": a == b, "!=": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[o or "="]


def term(key, typ, raw):
    v = raw.strip()
    low = v.lower()
    if not v:
        return lambda x: True
    if low in ("true", "false") or (typ == "bool" and low in ("yes", "no")):
        want = low in ("true", "yes")
        if typ == "bool":
            return lambda x: bool(x.get(key)) == want
        return lambda x: (x.get(key) not in (None, "", [])) == want
    if typ == "bool":
        want = low not in ("false", "no", "0", "n")
        return lambda x: bool(x.get(key)) == want
    if typ in ("number", "rating", "percent", "size"):
        o, n = _op(v)
        try:
            num = _size(n) if typ == "size" else float(n.rstrip("%"))
        except ValueError:
            raise SearchError(f"“{raw}” isn't a number")

        def f(x):
            val = x.get(key)
            if typ == "rating" and val is None:
                val = 0
            if val is None:
                return o == "!="
            if typ == "rating" and (o or "=") == "=":
                return round(val * 2) == round(num * 2) or (num == int(num) and int(val) == int(num))
            return _cmp(o, float(val), num)
        return f
    if typ == "date":
        o, n = _op(v)
        start, end = _period(n)

        def f(x):
            val = x.get(key)
            if not val:
                return o == "!="
            d = date.fromisoformat(val[:10])
            return {None: start <= d < end, "=": start <= d < end, "!=": not (start <= d < end), ">": d >= end,
                    ">=": d >= start, "<": d < start, "<=": d < end}[o]
        return f
    # text and lists
    if v.startswith("="):
        w = fold(v[1:])
        test = lambda s: fold(s) == w                     # noqa: E731
    elif v.startswith("~"):
        try:
            rx = re.compile(v[1:], re.I)
        except re.error:
            raise SearchError(f"“{v[1:]}” isn't a pattern")
        test = lambda s: bool(rx.search(str(s)))         # noqa: E731
    else:
        w = fold(v)
        test = lambda s: w in fold(s)                    # noqa: E731

    def f(x):
        val = x.get(key)
        if key == "series" and val:
            val = [val, f"{val} [{x.get('series_index') or 0:g}]"]
        if isinstance(val, list):
            return any(test(i) for i in val if i is not None)
        return val is not None and val != "" and test(val)
    return f


def search(books, q, cols):
    f = parse(q, cols)
    return [b for b in books if f(b)]


# ---------- sorting ----------
def sort(books, key, desc=False, cols=None):
    typ = next((c["type"] for c in (cols or []) if c["key"] == key), "text")

    def k(x):
        if key == "title":
            return fold(x.get("title_sort"))
        if key == "authors":
            return fold(x.get("author_sort")) or None
        if key == "series":
            return (fold(x.get("series_sort")), x.get("series_index") or 0) if x.get("series") else None
        v = x.get(key)
        if isinstance(v, list):
            return fold(", ".join(map(str, v))) or None
        if typ in ("number", "rating", "percent", "size"):
            return float(v) if v is not None else None
        if typ == "bool":
            return int(bool(v))
        return fold(v) if v not in (None, "") else None
    have = [b for b in books if k(b) is not None]
    none = [b for b in books if k(b) is None]
    have.sort(key=lambda x: fold(x.get("title_sort")))
    have.sort(key=k, reverse=bool(desc))
    none.sort(key=lambda x: fold(x.get("title_sort")))
    return have + none


# ---------- facets: the values to filter by, with counts (Calibre's Tag browser) ----------
FACETS = [("status", "Status"), ("tags", "Tags"), ("authors", "Authors"), ("series", "Series"), ("formats", "Formats"),
          ("languages", "Languages"), ("publisher", "Publishers"), ("rating", "Rating"), ("shelves", "Shelves")]


def facets(books, cols):
    out = []
    keys = FACETS + [(c["key"], c["label"]) for c in cols if c.get("custom") and c["type"] in ("text", "list", "rating")]
    for key, label in keys:
        counts = {}
        for b in books:
            v = b.get(key)
            for i in (v if isinstance(v, list) else [v]):
                if i is None or i == "":
                    continue
                counts[i] = counts.get(i, 0) + 1
        if not counts:
            continue
        if key == "rating":
            vals = sorted(counts.items(), key=lambda kv: -kv[0])
        elif key == "status":
            order = list(STATUS.values())
            vals = sorted(counts.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
        else:
            vals = sorted(counts.items(), key=lambda kv: (-kv[1], fold(kv[0])) if key in ("tags", "authors", "publisher") else fold(kv[0]))
        out.append({"key": key, "label": label, "values": [[v, n] for v, n in vals]})
    return out


# ---------- the view as a whole ----------
def view(conn, q="", sort_key="added", desc=True, private=False, with_facets=False):
    s = config.load_settings()
    books, cols = rows(conn, s, private)
    total = len(books)
    err = None
    try:
        found = search(books, q, cols)
    except SearchError as e:
        found, err = [], str(e)
    if sort_key not in {c["key"] for c in cols}:
        sort_key = "added"
    found = sort(found, sort_key, desc, cols)
    for b in found:
        b.pop("_hay", None)
    out = {"total": total, "count": len(found), "books": found, "columns": cols, "error": err, "sort": sort_key, "desc": bool(desc),
           "default_columns": DEFAULT_COLS, "views": s.get("catalog_views") or []}
    if with_facets:
        out["facets"] = facets(books, cols)
    return out


def cell(b, key, typ):
    v = b.get(key)
    if v is None:
        return ""
    if key == "series":
        return f"{v} [{b.get('series_index') or 0:g}]"
    if isinstance(v, list):
        return (" & " if key == "authors" else ", ").join(map(str, v))
    if typ == "bool":
        return "Yes" if v else "No"
    if typ == "size":
        return f"{v / 1024 / 1024:.1f}"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def to_csv(result, cols):
    known = {c["key"]: c for c in result["columns"]}
    keys = [k for k in cols if k in known] or [k for k in DEFAULT_COLS if k in known]
    buf = io.StringIO()
    buf.write("﻿")                                  # so Excel reads it as UTF-8
    w = csv.writer(buf)
    w.writerow([known[k]["label"] + (" (MB)" if known[k]["type"] == "size" else "") for k in keys])
    for b in result["books"]:
        w.writerow([cell(b, k, known[k]["type"]) for k in keys])
    return buf.getvalue()


def clean_views(views):
    """Saved views from the page: [{name, q, sort, desc, cols, widths}]."""
    out = []
    for v in views if isinstance(views, list) else []:
        if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"].strip():
            continue
        cols = [c for c in v.get("cols") or [] if isinstance(c, str) and len(c) < 60][:40]
        widths = {k: int(w) for k, w in (v.get("widths") or {}).items() if isinstance(k, str) and isinstance(w, (int, float)) and 40 <= w <= 900}
        out.append({"name": v["name"].strip()[:60], "q": str(v.get("q") or "")[:500], "sort": str(v.get("sort") or "added")[:60],
                    "desc": bool(v.get("desc")), "cols": cols, "widths": widths})
    seen, uniq = set(), []
    for v in out:
        if v["name"].lower() not in seen:
            seen.add(v["name"].lower())
            uniq.append(v)
    return uniq[:40]


# ---------- one book, everything there is to edit (the Edit sheet, bookedit.js) ----------
EDITABLE = ["title", "authors", "series", "series_index", "tags", "rating", "publisher", "published", "languages", "identifiers", "comments"]


def details(conn, cid, settings=None):
    """One Calibre book for editing: its fields (custom columns too), its description as text, its
    identifiers, its files and the choices each field has (existing tags, series, publishers…)."""
    settings = settings or config.load_settings()
    books, _cols = rows(conn, settings, private=True)
    custom = calibre_rows(settings)[1]
    b = next((x for x in books if x["calibre_id"] == cid), None)
    if not b:
        return None
    db = config.CALIBRE_DBS[0]
    c = read_only(db)
    try:
        com = c.execute("SELECT text FROM comments WHERE book = ?", (cid,)).fetchone()
        idents = {t: v for t, v in c.execute("SELECT type, val FROM identifiers WHERE book = ? ORDER BY type", (cid,))}
        path = c.execute("SELECT path FROM books WHERE id = ?", (cid,)).fetchone()[0]
        files = [{"format": f.upper(), "size": s, "name": n} for f, s, n in c.execute("SELECT format, uncompressed_size, name FROM data WHERE book = ? ORDER BY format", (cid,))]
        choices = {
            "tags": [r[0] for r in c.execute("SELECT name FROM tags ORDER BY name COLLATE NOCASE")],
            "series": [r[0] for r in c.execute("SELECT name FROM series ORDER BY sort COLLATE NOCASE")],
            "publisher": [r[0] for r in c.execute("SELECT name FROM publishers ORDER BY name COLLATE NOCASE")],
            "authors": [(r[0] or "").replace("|", ",") for r in c.execute("SELECT name FROM authors ORDER BY sort COLLATE NOCASE")],
            "languages": [r[0] for r in c.execute("SELECT lang_code FROM languages ORDER BY lang_code")],
        }
        for col in custom:
            if col["normalized"] and col["dtype"] in ("text", "series"):
                try:
                    choices[col["key"]] = [r[0] for r in c.execute(f"SELECT value FROM custom_column_{col['id']} ORDER BY value COLLATE NOCASE")]
                except Exception:  # noqa: BLE001
                    pass
    finally:
        c.close()
    html_text = com[0] if com and com[0] else ""
    text = re.sub(r"\n{3,}", "\n\n", html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", html_text)))).strip()
    for f in files:
        f["exists"] = (db.parent / path / f"{f['name']}.{f['format'].lower()}").exists()
    return b | {"comments": text, "comments_html": html_text, "identifiers": idents, "files": files, "choices": choices,
                "custom": [{"key": col["key"], "label": col["label"], "dtype": col["dtype"], "multi": col["multi"], "enum": col.get("enum")} for col in custom]}


def comments_html(text):
    """Plain text from the Edit sheet → Calibre's HTML description: a paragraph each."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in paras)


def book_file(cid, fmt):
    """The host path of a book's file in one format, or None."""
    db = config.CALIBRE_DBS[0]
    c = read_only(db)
    try:
        r = c.execute("SELECT b.path, d.name FROM books b JOIN data d ON d.book = b.id WHERE b.id = ? AND upper(d.format) = ?", (cid, fmt.upper())).fetchone()
    finally:
        c.close()
    if not r:
        return None
    p = db.parent / r[0] / f"{r[1]}.{fmt.lower()}"
    return p if p.exists() else None
