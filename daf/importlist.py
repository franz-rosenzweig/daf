"""Import list (All books → ⋯ → Import list): a list of books from somewhere else, matched against the
Calibre library the way Calibre's Import List plugin (kiwidude's, GPL) does it, then the ones Calibre
doesn't have added as empty books and the ones it has tagged or shelved (web/importlist.js; the writing
is calibrewrite's `add_empty` and `tags` ops).

The list comes in four ways:
- text, one book a line: "Title by Author", "Author - Title" or "Title - Author", "Title / Author",
  "Title (Author)", columns split by tabs, an ISBN alone; each line read on its own (form "auto"), or
  every line in one form, or the lines matched to a pattern with named groups, as the plugin does;
- a CSV or TSV file (or pasted columns), each column given a field by hand or guessed from the headings
  (Goodreads' and StoryGraph's exports are known);
- a web page: the plugin's predefined sites that still answer a plain fetch (SITES), or rows and fields
  picked out by XPath, the plugin's way;
- one of my Hardcover lists or shelves.

A row is {title, authors [..], series, series_index, isbn, published "YYYY-MM-DD", ids {type: value}}.
Matching goes the plugin's way: an identifier first (ISBN, Hardcover or Goodreads id), then title and
author from strict to forgiving (identical, similar, fuzzy: case, accents, articles, punctuation,
brackets, subtitles and initials aside, either order of the name), then the title alone for a row
without an author, and last Daf's own test (library.norm title and the author's surname). One book is a
match; several are offered to choose from, the first chosen.
"""
import base64
import csv
import gzip
import io
import re
import unicodedata
import zlib
from datetime import date

UA = "Daf/1.0 (personal reading app)"
FIELDS = ["title", "authors", "series", "series_index", "isbn", "published"]


class ListError(ValueError):
    pass


# ---------- tidying, as the plugin tidies (tab_common.tidy_*) ----------
SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "if", "in", "into", "nor", "of", "on", "or", "per", "the", "to", "vs", "via", "with"}


def titlecase(t):
    """A title in capitals ("THE HOLLOW", as the NYT lists them) → "The Hollow"; others are left alone."""
    if re.search(r"[a-z]", t) or not re.search(r"[A-Z].*[A-Z]", t):
        return t
    words, out = t.lower().split(" "), []
    for i, w in enumerate(words):
        if re.fullmatch(r"(?:i{1,3}|iv|vi{0,3}|ix|xi{0,3})[.,:;]?", w):
            out.append(w.upper())
        elif 0 < i < len(words) - 1 and w in SMALL and not out[-1].endswith(":"):
            out.append(w)
        else:
            out.append(re.sub(r"^(\W*)(\w)", lambda m: m.group(1) + m.group(2).upper(), w))
    return " ".join(out)


def tidy_title(t):
    t = titlecase(re.sub(r"\s+", " ", str(t or "")).strip())
    t = re.sub(r'[*"“”]', "", t)
    if t.endswith(" by"):                              # "Title by" from "Title by Author" split elsewhere
        t = t[:-3].strip()
    t = re.sub(r"^\d+\.(?=\s)", "", t)                   # a list's "12. "
    return t.strip(" ,.").strip()


SUFFIX = re.compile(r"(?i)^(jr|sr|ii|iii|iv|phd|ph\.d|md|m\.d)\.?$")


def _name_parts(p):
    """One author that may be "Last, First": turned round. "A B, C D" (two names) is two authors."""
    bits = [b.strip() for b in p.split(",") if b.strip()]
    if len(bits) < 2:
        return bits
    if len(bits) == 2:
        last, first = bits
        if SUFFIX.match(first):
            return [p.strip()]
        lw, fw = last.split(), first.split()
        initial = bool(re.search(r"(^|\s)[A-Z]\.?$", first)) or all(re.fullmatch(r"[A-Z]\.?", w) for w in fw)
        if len(lw) == 1 or len(fw) == 1 or initial:
            return [first + " " + last]
    return bits


def split_authors(a):
    """A list's author text → names: "&", ";", " and ", " with " separate them (Calibre's
    string_to_authors), "by " and a list's number go, "Last, First" is turned round, and "(Editor)"
    and the like are dropped."""
    if isinstance(a, (list, tuple)):
        out = []
        for x in a:
            out += split_authors(x)
        return list(dict.fromkeys(out))
    a = re.sub(r"\s+", " ", str(a or "")).strip().lstrip(",").strip()
    if a.lower().startswith("by "):
        a = a[3:].strip()
    a = re.sub(r"^\d+\.\s*", "", a)
    a = re.sub(r"\s*\([^)]*\)", "", a)
    a = a.replace("&&", "\uffff")
    a = re.sub(r"(?i),?\s+(and|with)\s+", "&", a)
    out = []
    for p in re.split(r"[&;]", a):
        p = p.strip().replace("\uffff", "&")
        for x in _name_parts(p) if p else []:
            x = x.strip()
            if x.endswith(".") and not re.search(r"(\b[A-Z]|\b(?:Jr|Sr|Dr|St|Ph\.D|M\.D))\.$", x):     # a sentence's full stop
                x = x[:-1].strip()
            out.append(x)
    return list(dict.fromkeys(x for x in out if x))


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def tidy_date(s):
    """A date in a list → "YYYY-MM-DD" (a year alone is its first of January), or None."""
    s = str(s or "").replace("(", "").replace(")", "").strip()
    if not s:
        return None
    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", s)            # the US way, 3/14/2001
        if m:
            mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            words = re.findall(r"[A-Za-z]+|\d+", s)
            y = next((int(w) for w in words if w.isdigit() and len(w) == 4), None)
            if y is None:
                return None
            mo = next((MONTHS[w[:3].lower()] for w in words if w[:3].lower() in MONTHS), 1)
            d = next((int(w) for w in words if w.isdigit() and len(w) <= 2 and 1 <= int(w) <= 31), 1) if mo != 1 or re.search(r"[A-Za-z]", s) else 1
    try:
        return date(y, mo, d).isoformat() if 100 < y < 3000 else None
    except ValueError:
        return f"{y:04d}-01-01" if 100 < y < 3000 else None


def isbn13(s):
    """An ISBN (10 or 13, with or without hyphens) → its 13 digits, or None."""
    d = re.sub(r"[^0-9Xx]", "", str(s or "")).upper()
    if len(d) == 13 and d.isdigit():
        return d
    if len(d) == 10 and d[:9].isdigit():
        core = "978" + d[:9]
        return core + str((10 - sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(core)) % 10) % 10)
    return None


def valid_isbn(s):
    d = re.sub(r"[^0-9Xx]", "", str(s or "")).upper()
    if len(d) == 10 and re.fullmatch(r"\d{9}[\dX]", d):
        return sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(d)) % 11 == 0
    if len(d) == 13 and d.isdigit() and d[:3] in ("978", "979"):
        return sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(d)) % 10 == 0
    return False


SERIES_IN_TITLE = re.compile(r"\s*\(([^()#]*?),?\s*(?:#|Book\s+|Vol\.?\s*|Volume\s+)(\d+(?:\.\d+)?)[^()]*\)\s*$", re.I)


def split_series(title):
    """Goodreads' "Title (Series, #2)" → (title, series, 2.0)."""
    m = SERIES_IN_TITLE.search(title or "")
    if not m or not m.group(1).strip() or not title[:m.start()].strip():
        return title, None, None
    return title[:m.start()].strip(), m.group(1).strip(" ,"), float(m.group(2))


def num(v):
    try:
        f = float(str(v).strip().lstrip("#"))
        return f if 0 <= f < 100000 else None
    except (TypeError, ValueError):
        return None


def make_row(title="", authors=None, series=None, series_index=None, isbn=None, published=None, ids=None):
    """A list's raw values → a row, tidied."""
    t = tidy_title(title)
    t2, s2, i2 = split_series(t)
    if s2 and not series:
        t, series, series_index = t2, s2, i2 if series_index in (None, "") else series_index
    elif s2:
        t = t2
    isbn = isbn13(isbn) if isbn and isbn13(isbn) else None
    ids = {str(k).strip().lower(): str(v).strip() for k, v in (ids or {}).items() if str(k).strip() and str(v or "").strip()}
    return {"title": t, "authors": split_authors(authors or []), "series": (re.sub(r"\s+", " ", str(series)).strip() or None) if series else None,
            "series_index": num(series_index) if series and series_index not in (None, "") else None,
            "isbn": isbn, "published": tidy_date(published), "ids": ids}


def clean_rows(rows):
    """Rows as the page sends them back (edited by hand), checked."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        a = r.get("authors")
        a = [str(x).strip()[:200] for x in a if str(x).strip()] if isinstance(a, list) else split_authors(str(a or ""))
        isbn = isbn13(r.get("isbn"))
        ids = r.get("ids") if isinstance(r.get("ids"), dict) else {}
        pub = r.get("published")
        out.append({"title": str(r.get("title") or "").strip()[:500], "authors": a[:20], "series": (str(r.get("series") or "").strip()[:300] or None),
                    "series_index": num(r.get("series_index")) if r.get("series_index") not in (None, "") else None, "isbn": isbn,
                    "published": pub if isinstance(pub, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", pub) else tidy_date(pub),
                    "ids": {str(k).strip().lower()[:40]: str(v).strip()[:300] for k, v in ids.items() if str(k).strip() and str(v or "").strip()},
                    "alt": bool(r.get("alt"))})
    return out[:2000]


# ---------- text: one book a line ----------
FORMS = ["auto", "by", "author-title", "title-author", "slash", "paren", "columns", "pattern"]
MARK = re.compile(r"^\s*(?:\d{1,4}[.)]\s+|[-*•·–—]\s+|#\d+\s+)")
ISBN_IN = re.compile(r"(?<![\w-])(?:ISBN(?:-1[03])?:?\s*)?([0-9][0-9-]{8,16}[0-9Xx])(?![\w-])", re.I)
DASH = re.compile(r"\s+[-–—]\s+")
NAME_SMALL = {"de", "van", "von", "der", "den", "le", "la", "du", "da", "di", "del", "della", "des", "ibn", "bin", "ben", "bat", "al", "el", "y", "st", "mc", "o"}
TITLE_WORDS = {"the", "a", "an", "of", "and", "in", "on", "to", "for", "with", "from", "at", "my", "your", "how", "what", "why", "is", "are", "book", "volume", "vol"}


def namey(s):
    """Does it look like a person's name: two to five words, each capitalised or an initial or a
    particle (van, de, ibn), no digits and none of a title's small words."""
    words = re.findall(r"[^\s]+", s or "")
    if not 2 <= len(words) <= 5 or re.search(r"\d", s):
        return False
    for w in words:
        lw = w.lower().strip(".,")
        if lw in TITLE_WORDS:
            return False
        if lw in NAME_SMALL or re.fullmatch(r"(?:[A-Z]\.)+[A-Z]?\.?|[A-Z]", w):
            continue
        if not w[:1].isupper():
            return False
    return True


def _isbn_out(line):
    for m in ISBN_IN.finditer(line):
        if valid_isbn(m.group(1)):
            return (line[:m.start()] + " " + line[m.end():]).strip(" ,;-–—|"), isbn13(m.group(1))
    return line, None


def parse_line(line, form="auto"):
    """One line → a row, or None for a line with nothing in it. A dash line whose order isn't clear
    from the words gets alt: the matcher tries it the other way round too."""
    line = re.sub(r"\s+$", "", str(line or "").replace("\u00a0", " "))
    if not line.strip():
        return None
    line, isbn = _isbn_out(MARK.sub("", line).strip())
    line = MARK.sub("", line).strip()
    if not line:
        return make_row(isbn=isbn) if isbn else None
    title, author, alt, order = line, "", False, None
    if form == "auto":
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
            title, author = parts[0], parts[1] if len(parts) > 1 else ""
        elif re.search(r",?\s+by\s+", line):
            parts = re.split(r",?\s+by\s+", line)            # the last "by": "Death by Black Hole by …"
            title, author = " by ".join(parts[:-1]), parts[-1]
        elif DASH.search(line):
            left, right = DASH.split(line, 1)
            if namey(left) and not namey(right):
                title, author, order = right, left, "at"
            elif namey(right) and not namey(left):
                title, author, order = left, right, "ta"
            else:
                title, author, order, alt = left, right, "?", True
        elif " / " in line:
            title, author = line.rsplit(" / ", 1)
        else:
            m = re.match(r"^(.*\S)\s*\(([^()]+)\)\s*$", line)
            if m and namey(m.group(2)) and not re.search(r"#|\bbook\b|\bvol", m.group(2), re.I):
                title, author = m.group(1), m.group(2)
    elif form == "by":
        parts = re.split(r",?\s+by\s+", line)
        title, author = (" by ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else (line, "")
    elif form in ("author-title", "title-author"):
        parts = DASH.split(line, 1)
        if len(parts) > 1:
            title, author = (parts[1], parts[0]) if form == "author-title" else (parts[0], parts[1])
    elif form == "slash":
        title, author = line.rsplit(" / ", 1) if " / " in line else (line, "")
    elif form == "paren":
        m = re.match(r"^(.*\S)\s*\(([^()]+)\)\s*$", line)
        if m:
            title, author = m.group(1), m.group(2)
    r = make_row(title, author, isbn=isbn)
    if alt and r["authors"]:
        r["alt"] = True
    if order:
        r["order"] = order
    return r if r["title"] or r["isbn"] else None


def parse_text(text, form="auto", pattern=""):
    """Pasted text → rows. Columns (tabs on most lines, or form "columns") go as a table instead:
    → {"table": …} for the page to choose the columns."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if form == "columns" or (form == "auto" and lines and sum("\t" in ln for ln in lines) >= max(2, len(lines) * .6)):
        return {"table": read_table(text.encode("utf-8"))}
    if form == "pattern":
        try:
            rx = re.compile(pattern or "")
        except re.error as e:
            raise ListError(f"The pattern doesn't work: {e}")
        names = set(rx.groupindex)
        if "title" not in names:
            raise ListError("The pattern needs a (?P<title>…) group")
        rows = []
        for ln in lines:
            m = rx.match(ln.strip())
            if not m:
                r = make_row(ln)
            else:
                g = {k: (v or "") for k, v in m.groupdict().items()}
                r = make_row(g.get("title"), g.get("authors") or g.get("author"), g.get("series"), g.get("series_index"),
                             g.get("isbn") or g.get("identifier:isbn"), g.get("published") or g.get("pubdate"))
            if r["title"] or r["isbn"]:
                rows.append(r)
        return {"rows": rows}
    rows = [r for r in (parse_line(ln, form if form in FORMS else "auto") for ln in lines) if r]
    # Dash lines that couldn't tell their order follow the ones that could (the matcher may still turn one round).
    orders = [r.pop("order", None) for r in rows]
    if orders.count("at") > orders.count("ta"):
        for r, o in zip(rows, orders):
            if o == "?" and r.get("authors"):
                r["title"], r["authors"] = " & ".join(r["authors"]), split_authors(r["title"])
    return {"rows": rows}


# ---------- tables: CSV, TSV, pasted columns ----------
def decode(data):
    if isinstance(data, str):
        return data
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_table(data, delimiter=None):
    """A file's bytes (or text) → {delimiter, rows [[cell…]] (the first 5,000), headings (a guess),
    columns {field: index} (a guess from the headings)}."""
    text = decode(data).replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise ListError("The file is empty")
    if delimiter not in ("\t", ",", ";", "|"):
        sample = [ln for ln in text.split("\n")[:30] if ln.strip()]
        best, score = ",", -1
        for d in ("\t", ",", ";", "|"):
            counts = [len(r) for r in csv.reader(sample, delimiter=d)]
            common = max(set(counts), key=counts.count) if counts else 1
            s = (counts.count(common) / len(counts)) * (common > 1) + (common > 1) * min(common, 6) / 100
            if s > score:
                best, score = d, s
        delimiter = best
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)][:5000]
    cols = guess_columns(rows[0]) if rows else {}
    return {"delimiter": delimiter, "rows": rows, "headings": bool(cols.get("title") is not None), "columns": cols if cols.get("title") is not None else {"title": 0, "authors": 1 if rows and len(rows[0]) > 1 else None}}


HEADS = {
    "title": ["title", "book title", "titel", "book"],
    "authors": ["authors", "author", "author(s)", "primary author", "creator", "author l-f", "author (last, first)", "author (first, last)", "writer"],
    "series": ["series", "series name"],
    "series_index": ["series_index", "series index", "series number", "series #", "number in series", "book number", "position", "#"],
    "isbn": ["isbn13", "isbn 13", "isbn-13", "isbn", "isbn/uid", "ean", "isbn10", "isbn 10", "isbn-10"],
    "published": ["pubdate", "published", "publication date", "date published", "original publication year", "year published", "first published", "publication year", "year"],
}


def guess_columns(header):
    """The plugin's "guess fields from the headings": {field: column index or None}."""
    h = [re.sub(r"\s+", " ", (c or "").replace("\ufeff", "").strip().lower().lstrip("#") or (c or "").strip()) for c in header]
    out = {}
    for field, names in HEADS.items():
        out[field] = next((h.index(n) for n in names if n in h), None)
    if "exclusive shelf" in h and "book id" in h:                 # Goodreads' export: its own id matches too
        out["goodreads"] = h.index("book id")
    return out


def table_rows(rows, columns, headings=True):
    """A table and which column is which → rows."""
    cols = {k: int(v) for k, v in (columns or {}).items() if v not in (None, "", -1) and str(v).lstrip("-").isdigit() and int(v) >= 0}
    if "title" not in cols and "isbn" not in cols:
        raise ListError("Which column has the title?")
    out = []
    for r in rows[1 if headings else 0:]:
        g = {k: (r[i] if i < len(r) else "") for k, i in cols.items()}
        isbn = re.sub(r'^="?|"$', "", g.get("isbn", "") or "")       # Goodreads writes ="0141439548"
        ids = {"goodreads": g["goodreads"]} if g.get("goodreads", "").isdigit() else {}
        row = make_row(g.get("title", ""), g.get("authors", ""), g.get("series"), g.get("series_index"), isbn, g.get("published"), ids)
        if row["title"] or row["isbn"]:
            out.append(row)
    return out


# ---------- web pages: the plugin's sites, and XPath of my own ----------
# Each config: rows (an XPath), then per field (XPath from the row, regex, strip?), as the plugin's
# KEY_WEB_XPATH_DATA. regex with strip=True is taken out of the text; strip=False keeps its group 1.
# Ported from the plugin's PREDEFINED_WEB_CONFIGS, its XPaths fixed for today's pages (and for lxml,
# which doesn't add a <tbody> a browser would). Checked against each site on 2026-11-13. Fantastic
# Fiction turns a plain fetch away (a human check), so it's left out; the New York Times does now and then.
GR_ID = (r"/book/show/(\d+)", False)
GR_PARENS = r"\s*\((?![^)]*#)[^)]*\)"                # "(Paperback)" goes; "(Series, #2)" stays for make_row
CONFIGS = {
    "Goodreads": {
        "rows": '//tr[.//a[contains(@class,"bookTitle")]]',
        "title": ('.//a[contains(@class,"bookTitle")]//text()', GR_PARENS, True),
        "authors": ('.//a[contains(@class,"authorName")]/span/text()', None, True),
        "goodreads": ('.//a[contains(@class,"bookTitle")]/@href',) + GR_ID,
    },
    "Goodreads Shelf": {
        "rows": '//div[contains(@class,"elementList")][.//a[contains(@class,"bookTitle")]]',
        "title": ('.//a[contains(@class,"bookTitle")]//text()', GR_PARENS, True),
        "authors": ('.//a[contains(@class,"authorName")]/span/text()', None, True),
        "goodreads": ('.//a[contains(@class,"bookTitle")]/@href',) + GR_ID,
    },
    "Goodreads (new pages)": {
        "rows": '//article[contains(@class,"BookListItem")]',
        "title": ('.//a[@data-testid="bookTitle"]//text()', GR_PARENS, True),
        "authors": ('.//*[@data-testid="name"]/text()', None, True),
        "goodreads": ('.//a[@data-testid="bookTitle"]/@href',) + GR_ID,
    },
    "Amazon": {
        "rows": '//div[@id="gridItemRoot"]',
        "title": ('(.//a[contains(@class,"a-link-normal")]//div[contains(@class,"line-clamp")])[1]/text()', r":.*|\(.*\)", True),
        "authors": ('(.//div[contains(@class,"a-row") and contains(@class,"a-size-small")])[1]//text()[normalize-space()]', None, True),
        "amazon": ('.//a[contains(@class,"a-link-normal")][contains(@href,"/dp/")][1]/@href', r"/dp/([0-9A-Z]{10})", False),
    },
    "NY Times": {
        "rows": '//article[@itemtype="https://schema.org/Book"]',
        "title": ('.//h3[@itemprop="name"]//text()', None, True),
        "authors": ('.//p[@itemprop="author"]//text()', None, True),
        "isbn": ('.//a[contains(@href,"97")]/@href', r"(97[89]\d{10})", False),
    },
    "Wikipedia": {
        "rows": '//table[contains(@class,"wikitable")]//tr[td]',
        "title": ('(td[2]//i)[1]//text()', None, True),
        "authors": ('td[1]//span[contains(@class,"fn")]//a/text() | td[1][not(.//span[contains(@class,"fn")])]//a/text()', None, True),
    },
}


def _gr_month():
    t = date.today()
    return f"https://www.goodreads.com/book/popular_by_date/{t.year}/{t.month}"


def _gr_year():
    return f"https://www.goodreads.com/book/popular_by_date/{date.today().year}"


# (name, url or a function for today's, config) – the plugin's predefined pages that still work.
_AMZ, _AUK = "https://www.amazon.com/", "https://www.amazon.co.uk/"
_UK = [("Action", "Adventure-Stories-Action", "275035"), ("Children", "Childrens", "69"), ("Contemporary", "Contemporary-Fiction", "590756"),
       ("Crime", "Crime-Thrillers-Mystery", "72"), ("Fantasy", "Fantasy", "279254"), ("Fiction", "Fiction", "62"),
       ("Historical", "Historical-Fiction", "10790401"), ("Horror", "Horror", "63"), ("Humour", "Humorous-Fiction", "426359031"),
       ("Romance", "Romance", "88"), ("Science Fiction", "Science-Fiction", "279292"), ("Westerns", "Westerns", "275065"),
       ("Women", "Women-Writers-Fiction", "590760")]
SITES = [(f"Amazon UK: Bestsellers: {n}", f"{_AUK}Bestsellers-Books-{p}/zgbs/books/{i}/", "Amazon") for n, p, i in _UK] + \
    [(f"Amazon UK: New Releases: {n}", f"{_AUK}gp/new-releases/books/{i}/", "Amazon") for n, _p, i in _UK] + [
    ("Amazon USA: Bestsellers: Action", _AMZ + "Best-Sellers-Books-Action-Adventure-Fiction/zgbs/books/720360/", "Amazon"),
    ("Amazon USA: Bestsellers: Children", _AMZ + "Best-Sellers-Books-Childrens/zgbs/books/4/", "Amazon"),
    ("Amazon USA: Bestsellers: Contemporary", _AMZ + "Best-Sellers-Books-Contemporary-Literature-Fiction/zgbs/books/10129/", "Amazon"),
    ("Amazon USA: Bestsellers: Crime", _AMZ + "Best-Sellers-Books-Mystery-Thriller-Suspense/zgbs/books/18/", "Amazon"),
    ("Amazon USA: Bestsellers: Fantasy", _AMZ + "Best-Sellers-Books-Fantasy/zgbs/books/16190/", "Amazon"),
    ("Amazon USA: Bestsellers: Fiction", _AMZ + "Best-Sellers-Books-Literature-Fiction/zgbs/books/17/", "Amazon"),
    ("Amazon USA: Bestsellers: Historical", _AMZ + "Best-Sellers-Books-Historical-Fiction/zgbs/books/10177/", "Amazon"),
    ("Amazon USA: Bestsellers: Horror", _AMZ + "Best-Sellers-Books-Horror-Literature-Fiction/zgbs/books/49/", "Amazon"),
    ("Amazon USA: Bestsellers: Humour", _AMZ + "Best-Sellers-Books-Humorous-Fiction/zgbs/books/4465/", "Amazon"),
    ("Amazon USA: Bestsellers: Romance", _AMZ + "Best-Sellers-Books-Romance/zgbs/books/23/", "Amazon"),
    ("Amazon USA: Bestsellers: Science Fiction", _AMZ + "Best-Sellers-Books-Science-Fiction/zgbs/books/16272/", "Amazon"),
    ("Amazon USA: Bestsellers: Westerns", _AMZ + "Best-Sellers-Books-Western-Fiction/zgbs/books/10197/", "Amazon"),
    ("Amazon USA: Bestsellers: Women", _AMZ + "Best-Sellers-Books-Womens-Literature-Fiction/zgbs/books/542654/", "Amazon"),
    ("Amazon USA: Bestsellers: Young Adult", _AMZ + "Best-Sellers-Books-Teen/zgbs/books/28/", "Amazon"),
    ("Amazon USA: New Releases: Action", _AMZ + "gp/new-releases/books/720360/", "Amazon"),
    ("Amazon USA: New Releases: Children", _AMZ + "gp/new-releases/books/4/", "Amazon"),
    ("Amazon USA: New Releases: Contemporary", _AMZ + "gp/new-releases/books/10129/", "Amazon"),
    ("Amazon USA: New Releases: Crime", _AMZ + "gp/new-releases/books/18/", "Amazon"),
    ("Amazon USA: New Releases: Fantasy", _AMZ + "gp/new-releases/books/16190/", "Amazon"),
    ("Amazon USA: New Releases: Fiction", _AMZ + "gp/new-releases/books/17/", "Amazon"),
    ("Amazon USA: New Releases: Historical", _AMZ + "gp/new-releases/books/10177/", "Amazon"),
    ("Amazon USA: New Releases: Horror", _AMZ + "gp/new-releases/books/49/", "Amazon"),
    ("Amazon USA: New Releases: Humour", _AMZ + "gp/new-releases/books/4465/", "Amazon"),
    ("Amazon USA: New Releases: Romance", _AMZ + "gp/new-releases/books/23/", "Amazon"),
    ("Amazon USA: New Releases: Science Fiction", _AMZ + "gp/new-releases/books/16272/", "Amazon"),
    ("Amazon USA: New Releases: Westerns", _AMZ + "gp/new-releases/books/10197/", "Amazon"),
    ("Amazon USA: New Releases: Women", _AMZ + "gp/new-releases/books/542654/", "Amazon"),
    ("Amazon USA: New Releases: Young Adult", _AMZ + "gp/new-releases/books/28/", "Amazon"),
    ("Goodreads: Awards: Hugo Award", "https://www.goodreads.com/award/show/9-hugo-award", "Goodreads"),
    ("Goodreads: Listopia: Best Books Ever", "https://www.goodreads.com/list/show/1.Best_Books_Ever", "Goodreads"),
    ("Goodreads: Most Read", "https://www.goodreads.com/book/most_read", "Goodreads"),
    ("Goodreads: Popular: This Month", _gr_month, "Goodreads (new pages)"),
    ("Goodreads: Popular: This Year", _gr_year, "Goodreads (new pages)"),
    ("Goodreads: Search Result", "https://www.goodreads.com/search?q=", "Goodreads"),
] + [(f"Goodreads: Shelves: {n}", f"https://www.goodreads.com/shelf/show/{s}", "Goodreads Shelf") for n, s in [
    ("Adventure", "adventure"), ("Chick-Lit", "chick-lit"), ("Childrens", "childrens"), ("Contemporary", "contemporary"),
    ("Currently Reading", "currently-reading"), ("Fantasy", "fantasy"), ("Historical", "historical-fiction"), ("Humor", "humor"),
    ("Horror", "horror"), ("Non-Fiction", "non-fiction"), ("Romance", "romance"), ("Science-Fiction", "science-fiction"),
    ("Thriller", "thriller"), ("To Read", "to-read"), ("Western", "western"), ("Young-Adult", "young-adult")]] + [
    ("NY Times Bestsellers: Fiction eBooks", "https://www.nytimes.com/best-sellers-books/e-book-fiction/list.html", "NY Times"),
    ("NY Times Bestsellers: NonFiction eBooks", "https://www.nytimes.com/best-sellers-books/e-book-nonfiction/list.html", "NY Times"),
    ("Wikipedia: Hugo Best Novel", "https://en.wikipedia.org/wiki/Hugo_Award_for_Best_Novel", "Wikipedia"),
    ("Wikipedia: Nebula Best Novel", "https://en.wikipedia.org/wiki/Nebula_Award_for_Best_Novel", "Wikipedia"),
]


def sites():
    return [{"name": n, "url": u() if callable(u) else u, "config": c} for n, u, c in SITES]


def config_for(url):
    """The config a page address goes with (a page of the same site laid out the same way)."""
    from urllib.parse import urlparse
    u = urlparse(url or "")
    host, path = (u.hostname or "").lower(), u.path
    if host.endswith("goodreads.com"):
        if path.startswith("/shelf/show"):
            return "Goodreads Shelf"
        if path.startswith("/book/popular_by_date") or path.startswith("/genres/new_releases"):
            return "Goodreads (new pages)"
        return "Goodreads"
    if re.search(r"(^|\.)amazon\.(com|co\.uk)$", host):
        return "Amazon"
    if host.endswith("nytimes.com"):
        return "NY Times"
    if host.endswith("wikipedia.org"):
        return "Wikipedia"
    return None


def _public(url):
    import ipaddress
    import socket
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ListError("A page's address starts with http")
    try:
        for info in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip in ipaddress.ip_network("100.64.0.0/10"):
                raise ListError("Not an address on the web")
    except socket.gaierror:
        raise ListError("No such address")


def fetch(url, timeout=30):
    """A page's HTML, fetched the plain way (no browser, no script run), as Daf."""
    import urllib.error
    import urllib.request
    _public(url)
    import http.cookiejar
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en"})
    # A cookie jar for this one fetch: some sites set a cookie and send the page back to itself.
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    try:
        with opener.open(req, timeout=timeout) as r:
            data, charset, enc = r.read(8 * 1024 * 1024), r.headers.get_content_charset(), (r.headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as e:
        raise ListError(f"The site turned Daf away ({e.code})" if e.code in (401, 403, 405, 429, 503) else f"The page didn't come ({e.code})")
    except Exception as e:  # noqa: BLE001 - the page says what went wrong
        raise ListError(f"The page didn't come: {getattr(e, 'reason', e)}")
    if data[:2] == b"\x1f\x8b":                    # some sites send gzip whether asked or not
        data = gzip.decompress(data)
    elif enc == "deflate":
        data = zlib.decompress(data)
    html = data.decode(charset or "utf-8", errors="replace")
    if re.search(r"<title>\s*(Human Verification|Just a moment|Attention Required|Robot Check)", html[:4000], re.I) or \
            ("captcha" in html[:20000].lower() and len(html) < 20000):
        raise ListError("The site turned Daf away")
    return html


def page_urls(url):
    """The plugin's page ranges: "…page={1-5}…" is pages 1 to 5 (10 at most: the answer has to come within a minute or so)."""
    m = re.search(r"\{(\d+)-(\d+)\}", url)
    if not m:
        return [url]
    a, b = int(m.group(1)), int(m.group(2))
    return [url[:m.start()] + str(n) + url[m.end():] for n in range(a, min(b, a + 9) + 1)]


def _texts(node, xp):
    try:
        got = node.xpath(xp)
    except Exception as e:  # noqa: BLE001 - lxml's XPath errors
        raise ListError(f"That XPath doesn't work: {e}")
    if not isinstance(got, list):
        got = [got]
    out = []
    for g in got:
        s = g.text_content() if hasattr(g, "text_content") else str(g)
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            out.append(s)
    return out


def _apply(v, regex, keep_group):
    if not regex:
        return v
    if keep_group is False:
        m = re.search(regex, v)
        return (m.group(1) if m.groups() else m.group(0)) if m else ""
    return re.sub(regex, "", v)


def extract(html, cfg):
    """A page and a config → rows, the plugin's way: each row's values per field; a field with one
    value (the author of a whole page) goes with every title in the row."""
    import lxml.html
    try:
        root = lxml.html.fromstring(html)
    except Exception as e:  # noqa: BLE001
        raise ListError(f"Daf couldn't read the page: {e}")
    rows_xp = (cfg.get("rows") or "").strip()
    nodes = _nodes(root, rows_xp) if rows_xp else [root]
    out = []
    for node in nodes:
        vals = {}
        for field, spec in cfg.items():
            if field == "rows" or not spec or not spec[0]:
                continue
            xp, regex, strip = (list(spec) + [None, True])[:3]
            got = [_apply(v, regex, False if strip is False else True) for v in _texts(node, xp)]
            got = [g.strip() for g in got if g and g.strip()]
            if field == "authors" and len(got) > 1 and rows_xp:
                got = [" & ".join(got)]
            if field == "series_index":
                got = [g for g in got if num(g) is not None]
            vals[field] = got
        n = len(vals.get("title") or [])
        for i in range(n):
            def pick(f, shared=False):
                v = vals.get(f) or []
                if len(v) == 1 and shared:
                    return v[0]
                return v[i] if i < len(v) else ""
            ids = {k: pick(k) for k in vals if k not in FIELDS and pick(k)}
            r = make_row(pick("title"), pick("authors", True), pick("series", True), pick("series_index"), pick("isbn"), pick("published"), ids)
            if r["title"]:
                out.append(r)
    return out


def _nodes(root, xp):
    try:
        got = root.xpath(xp)
    except Exception as e:  # noqa: BLE001
        raise ListError(f"That XPath doesn't work: {e}")
    return [g for g in (got if isinstance(got, list) else []) if hasattr(g, "xpath")]


def custom_config(x):
    """The page's own XPaths: {rows, title, authors, series, series_index, isbn, published}."""
    x = x if isinstance(x, dict) else {}
    cfg = {"rows": str(x.get("rows") or "").strip()[:500]}
    for f in FIELDS:
        v = str(x.get(f) or "").strip()[:500]
        if v:
            cfg[f] = (v, None, True)
    if "title" not in cfg:
        raise ListError("An XPath for the title, please")
    return cfg


def read_web(url, config=None, xpaths=None):
    url = str(url or "").strip()
    if not url:
        raise ListError("A page's address, please")
    if not re.match(r"(?i)^https?://", url):
        url = "https://" + url
    _public(url)
    cfg = custom_config(xpaths) if xpaths else CONFIGS.get(config or "") or CONFIGS.get(config_for(url) or "")
    if not cfg:
        raise ListError("Daf doesn't know that site: give it the XPaths")
    rows = []
    for u in page_urls(url):
        rows += extract(fetch(u), cfg)
    seen, uniq = set(), []
    for r in rows:                                   # the same book twice on a page (two tables) once
        k = (r["title"].lower(), tuple(a.lower() for a in r["authors"]))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


# ---------- Hardcover: my lists and shelves ----------
HC_BOOK = """id title slug release_date cached_contributors book_series { position featured series { name } }
  default_physical_edition { isbn_13 isbn_10 } default_ebook_edition { isbn_13 isbn_10 }"""
HC_SHELVES = [(1, "Want to read"), (2, "Currently reading"), (3, "Read"), (4, "Paused"), (5, "Did not finish")]


def hardcover_sources():
    """[{key, name, count}]: my Hardcover lists, then the shelves."""
    from . import hardcover
    d = hardcover.gql("{ me { lists(order_by:{name:asc}) { id name books_count } } }")["me"][0]
    out = [{"key": f"list:{x['id']}", "name": x["name"], "count": x.get("books_count")} for x in d["lists"]]
    return out + [{"key": f"status:{s}", "name": n, "count": None} for s, n in HC_SHELVES]


def _hc_row(bk):
    cs = [c for c in (bk.get("cached_contributors") or []) if c.get("author") and c.get("contribution") in (None, "", "Author")]
    cs = cs or [c for c in (bk.get("cached_contributors") or []) if c.get("author")][:1]
    named = [s for s in bk.get("book_series") or [] if (s.get("series") or {}).get("name")]
    ser = next((s for s in named if s.get("featured")), named[0] if named else None)
    ed = bk.get("default_physical_edition") or bk.get("default_ebook_edition") or {}
    ids = {"hardcover-book": str(bk["id"])}
    if bk.get("slug"):
        ids["hardcover"] = bk["slug"]
    return make_row(bk.get("title") or "", [c["author"]["name"] for c in cs[:5]], (ser or {}).get("series", {}).get("name") if ser else None,
                    (ser or {}).get("position"), ed.get("isbn_13") or ed.get("isbn_10"), bk.get("release_date"), ids)


def read_hardcover(key):
    from . import hardcover
    kind, _, val = str(key or "").partition(":")
    if not val.isdigit():
        raise ListError("Which list?")
    if kind == "list":
        d = hardcover.gql("query($id:Int!){ lists_by_pk(id:$id){ list_books(order_by:{position:asc}) { book { %s } } } }" % HC_BOOK, {"id": int(val)})
        lst = d.get("lists_by_pk")
        if not lst:
            raise ListError("Hardcover has no such list")
        books = [x["book"] for x in lst["list_books"] if x.get("book")]
    elif kind == "status":
        d = hardcover.gql("query($s:Int!){ me { user_books(where:{status_id:{_eq:$s}}, order_by:{updated_at:desc}) { book { %s } } } }" % HC_BOOK, {"s": int(val)})
        books = [x["book"] for x in d["me"][0]["user_books"] if x.get("book")]
    else:
        raise ListError("Which list?")
    return [_hc_row(b) for b in books]


def lookup_isbns(isbns):
    """{isbn13: {title, authors, series, series_index, published, ids}} from Hardcover's editions, for
    rows that came as an ISBN alone."""
    from . import hardcover
    isbns = [i for i in dict.fromkeys(isbns) if i][:200]
    if not isbns:
        return {}
    q = ("query($i:[String!]){ editions(where:{isbn_13:{_in:$i}}, limit:400){ isbn_13 title release_date book { %s } } }" % HC_BOOK)
    d = hardcover.gql(q, {"i": isbns})
    out = {}
    for e in d.get("editions") or []:
        if e.get("isbn_13") in out or not e.get("book"):
            continue
        r = _hc_row(e["book"])
        r["series"] = r["series_index"] = None          # an edition's series is often a publisher's (graded readers)
        r["title"] = tidy_title(e.get("title") or "") or r["title"]
        r["published"] = tidy_date(e.get("release_date")) or r["published"]
        out[e["isbn_13"]] = r
    return out


# ---------- matching (the plugin's algorithms.py) ----------
def _plain(s):
    """get_udc().decode, near enough: accents and points off, other scripts kept."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "")) if not unicodedata.combining(ch))


SIMILAR = [(re.compile(p, re.I), r) for p, r in [(r"(\[.*\])", ""), (r"(\(.*\))", ""), (r"&", " and "), (r"[{}<>'\";,:#?]", ""),
                                                  (r"^(a|the|an)\s+", ""), (r"[-._]", " "), (r"\s+", " ")]]
FUZZY = [(re.compile(p, re.I), r) for p, r in [(r"(\(.*\))", ""), (r"[({\[](\d{4}|omnibus|anthology|hardcover|paperback|mass\s*market|edition|ed\.|series|trilogy)[\])}]", ""),
                                                (r"[({\[].*?(edition|ed.).*?[\]})]", ""), (r"(\d+),(\d+)", r"\1\2"), (r"(\s-)", " "), (r"'(?!s)", ""),
                                                (r"[:,;+!@#$%^&*(){}.`~\"\s\[\]/]", " ")]]
SUBTITLE = re.compile(r"([\[\{].*?[\]\}]|[/:\\].*$)")
AU_SKIP = {"von", "van", "jr", "sr", "i", "ii", "iii", "second", "third", "md", "phd"}


def t_identical(t):
    return (t or "").lower()


def t_similar(t):
    t = _plain(t).strip().lower()
    for p, r in SIMILAR:
        t = p.sub(r, t)
    return t.strip()


def t_fuzzy(t):
    t = t or ""
    if len(SUBTITLE.sub("", t)) > 1:
        t = SUBTITLE.sub("", t)
    for p, r in FUZZY:
        t = p.sub(r, t)
    return "".join(w.lower() for w in _plain(t).split() if w.lower() != "the")


def author_tokens(a):
    au = _plain(re.sub(r"[-+.:;]", " ", a or ""))
    parts = au.split()
    if "," in au:
        parts = parts[1:] + parts[:1]
    out = []
    for tok in parts:
        tok = re.sub(r"[,!@#$%^&*(){}`~\"\s\[\]/]", "", tok).strip()
        if tok and tok.lower() not in AU_SKIP:
            out.append(tok.lower())
    return out


def a_identical(a):
    return (a or "").lower(), None


def a_similar(a):
    toks = [t for t in author_tokens(a) if len(t) > 1]
    h = " ".join(toks)
    rev = " ".join(toks[1:] + toks[:1]) if len(toks) > 1 else None
    return h, rev


TA_TIERS = [("identical", t_identical, a_identical), ("similar", t_similar, a_identical), ("similar", t_identical, a_similar),
            ("similar", t_similar, a_similar), ("fuzzy", t_fuzzy, a_similar)]
T_TIERS = [("title", t_identical), ("title", t_similar)]


def _id_key(typ, val):
    typ = str(typ).lower().strip()
    if typ in ("isbn", "isbn13", "isbn10"):
        i = isbn13(val)
        return ("isbn", i) if i else None
    return (typ, str(val).strip().lower()) if str(val).strip() else None


class Library:
    """The library hashed every way the tiers look (the plugin's LibraryHashBuilder)."""

    def __init__(self, books):
        self.books = {b["calibre_id"]: b for b in books}
        self.ids, self.maps, self.tmaps, self.authors = {}, [{} for _ in TA_TIERS], [{} for _ in T_TIERS], set()
        for cid, b in self.books.items():
            for ident in b.get("identifiers") or []:
                typ, _, val = str(ident).partition(":")
                k = _id_key(typ, val)
                if k:
                    self.ids.setdefault(k, set()).add(cid)
            if b.get("isbn"):
                k = _id_key("isbn", b["isbn"])
                if k:
                    self.ids.setdefault(k, set()).add(cid)
            for n, (_name, tf, af) in enumerate(TA_TIERS):
                th = tf(b.get("title") or "")
                for a in b.get("authors") or []:
                    h, rev = af(a)
                    self.maps[n].setdefault(th + "|" + h, set()).add(cid)
                    if rev and rev != h:
                        self.maps[n].setdefault(th + "|" + rev, set()).add(cid)
            for n, (_name, tf) in enumerate(T_TIERS):
                self.tmaps[n].setdefault(tf(b.get("title") or ""), set()).add(cid)
            for a in b.get("authors") or []:
                self.authors.update(h for h in a_similar(a) if h)

    def find(self, row):
        """→ (how, [calibre ids]) or (None, [])."""
        for typ, val in sorted((row.get("ids") or {}).items()):
            k = _id_key(typ, val)
            if k and k in self.ids:
                return typ if typ != "hardcover-book" else "hardcover", sorted(self.ids[k])
        if row.get("isbn") and ("isbn", row["isbn"]) in self.ids:
            return "isbn", sorted(self.ids[("isbn", row["isbn"])])
        title, authors = row.get("title") or "", row.get("authors") or []
        if not title:
            return None, []
        if authors:
            for n, (name, tf, af) in enumerate(TA_TIERS):
                th, hit = tf(title), set()
                for a in authors:
                    h, rev = af(a)
                    hit |= self.maps[n].get(th + "|" + h, set())
                    if rev:
                        hit |= self.maps[n].get(th + "|" + rev, set())
                if hit:
                    return name, sorted(hit)
            hit = self._daf_same(title, authors)
            if hit:
                return "fuzzy", hit
            return None, []
        for n, (name, tf) in enumerate(T_TIERS):
            hit = self.tmaps[n].get(tf(title))
            if hit:
                return name, sorted(hit)
        return None, []

    def _daf_same(self, title, authors):
        """Daf's own test (calibrefind.same_book): the library.norm title, or one the start of the
        other, and the first author's surname among the book's authors."""
        from .catalog import fold
        from .library import norm, surname
        a = norm(title)
        who = surname(authors[0]) if authors else ""
        if not a or not who:
            return []
        out = []
        for cid, b in self.books.items():
            n = norm(b.get("title") or "")
            if n and (n == a or n.startswith(a + " ") or a.startswith(n + " ")) and \
                    who in re.sub(r"[^a-z]+", " ", fold(" ".join(b.get("authors") or []))).split():
                out.append(cid)
        return sorted(out)

    def known_author(self, name):
        h, rev = a_similar(name)
        return bool(h) and (h in self.authors or (rev and rev in self.authors))

    def card(self, cid):
        b = self.books.get(cid) or {}
        return {"id": cid, "title": b.get("title"), "authors": b.get("authors") or [], "formats": b.get("formats") or [],
                "series": b.get("series"), "series_index": b.get("series_index")}


def match(rows, books):
    """Each row with what it matched: {…row, match: {id, title, authors, formats} | None, how, choices}.
    A row with alt (a dash line whose order wasn't sure) is turned round when only that way matches,
    or, matching nothing, when only that way names an author the library knows."""
    lib = books if isinstance(books, Library) else Library(books)
    out = []
    for r in rows:
        r = dict(r)
        how, ids = lib.find(r)
        if not ids and r.get("alt") and r.get("authors"):
            swapped = dict(r, title=" & ".join(r["authors"]), authors=split_authors(r["title"]))
            how2, ids2 = lib.find(swapped)
            if ids2 or (not any(lib.known_author(a) for a in r["authors"]) and lib.known_author(swapped["authors"][0] if swapped["authors"] else "")):
                r, how, ids = swapped, how2, ids2
        r.pop("alt", None)
        # several: the one with a file first, then the oldest
        ids = sorted(ids, key=lambda i: (not (lib.books.get(i) or {}).get("formats"), i))
        r["match"] = lib.card(ids[0]) if ids else None
        r["how"] = how
        r["choices"] = [lib.card(i) for i in ids[:8]] if len(ids) > 1 else []
        out.append(r)
    return out


def search(books, q, limit=30):
    """The library's books for a few words (a row's match by hand): every word in the title or authors."""
    from .catalog import fold
    words = fold(q).split()
    if not words:
        return []
    out = []
    for b in books:
        hay = fold(" ".join([b.get("title") or ""] + list(b.get("authors") or []) + [b.get("series") or ""]))
        if all(w in hay for w in words):
            out.append(b)
    out.sort(key=lambda b: (not fold(b.get("title") or "").startswith(words[0]), fold(b.get("title") or "")))
    return [{"id": b["calibre_id"], "title": b.get("title"), "authors": b.get("authors") or [], "formats": b.get("formats") or [],
             "series": b.get("series"), "series_index": b.get("series_index")} for b in out[:limit]]


# ---------- the list in (one call for every way in) ----------
def read(src, conn=None):
    """{source: text | table | web | hardcover, …} → {rows} or {table} (columns to choose first)."""
    src = src if isinstance(src, dict) else {}
    kind = src.get("source")
    if kind == "text":
        r = parse_text(str(src.get("text") or "")[:2_000_000], str(src.get("form") or "auto"), str(src.get("pattern") or ""))
        if "table" in r:
            r["table"] = r["table"] | {"rows": r["table"]["rows"][:12], "count": len(r["table"]["rows"])}
        return r
    if kind == "table":                                  # a file (base64) or pasted columns, then its columns
        if src.get("data"):
            try:
                raw = base64.b64decode(str(src["data"]))
            except ValueError:
                raise ListError("Daf couldn't read the file")
        else:
            raw = str(src.get("text") or "").encode("utf-8")
        if len(raw) > 20 * 1024 * 1024:
            raise ListError("The file is too big")
        t = read_table(raw, src.get("delimiter"))
        if not src.get("columns"):
            return {"table": t | {"rows": t["rows"][:12], "count": len(t["rows"])}}
        headings = t["headings"] if src.get("headings") is None else bool(src.get("headings"))
        return {"rows": table_rows(t["rows"], src["columns"], headings)}
    if kind == "web":
        return {"rows": read_web(src.get("url"), src.get("config"), src.get("xpaths"))}
    if kind == "hardcover":
        return {"rows": read_hardcover(src.get("list"))}
    raise ListError("Where is the list from?")


def fill_isbn_rows(rows):
    """Rows that are an ISBN alone get their title and author from Hardcover, when it has the ISBN."""
    want = [r["isbn"] for r in rows if r.get("isbn") and not r.get("title")]
    if not want:
        return rows
    try:
        got = lookup_isbns(want)
    except Exception:  # noqa: BLE001 - without Hardcover the row stays an ISBN
        return rows
    for r in rows:
        g = got.get(r.get("isbn")) if not r.get("title") else None
        if g:
            for k in ("title", "authors", "published"):
                if g.get(k) and not r.get(k):
                    r[k] = g[k]
            r["ids"] = {**g.get("ids", {}), **(r.get("ids") or {})}
    return rows


def prepare(rows, books):
    """Rows read → matched: an ISBN alone that the library doesn't have is looked up first."""
    lib = Library(books)
    fill_isbn_rows([r for r in rows if r.get("isbn") and not r.get("title") and ("isbn", r["isbn"]) not in lib.ids])
    return match(rows, lib)


# ---------- what to do: the books Calibre doesn't have, as empty books ----------
def empty_books(rows, tags=None, read=None):
    """Rows → add_empty's books: title (or Unknown), authors, series, its number, published, ISBN and
    the list's identifiers, the tags, and Read's choice ({"#read": "Planning"})."""
    out = []
    for r in rows:
        ids = {k: v for k, v in (r.get("ids") or {}).items() if k in ("hardcover-book", "hardcover", "goodreads", "amazon")}
        if r.get("isbn"):
            ids["isbn"] = r["isbn"]
        b = {"title": r.get("title") or "Unknown", "authors": r.get("authors") or ["Unknown"], "identifiers": ids}
        if r.get("series"):
            b["series"] = r["series"]
            if r.get("series_index") is not None:
                b["series_index"] = r["series_index"]
        if r.get("published"):
            b["pubdate"] = r["published"]
        if tags:
            b["tags"] = list(tags)
        if read:
            b["fields"] = dict(read)
        out.append(b)
    return out


def read_column(settings):
    """Calibre's Read column and its choice for To read (calibrekeep): {key, label, choice} or None."""
    import sqlite3
    from . import calibrekeep, config
    label = (settings.get("calibre_read_column") or "#read").lstrip("#")
    try:
        c = sqlite3.connect(f"file:{config.CALIBRE_DBS[0]}?mode=ro", uri=True)
        try:
            r = c.execute("SELECT name, datatype, display FROM custom_columns WHERE label = ? AND mark_for_delete = 0", (label,)).fetchone()
        finally:
            c.close()
    except sqlite3.Error:
        return None
    if not r or r[1] != "enumeration":
        return None
    choice = calibrekeep.read_choices(r[2]).get("to-read")
    if not choice:
        return None
    return {"key": "#" + label, "label": r[0] or label, "choice": choice}


def tags_from(s):
    """"Hugo, Award" → ["Hugo", "Award"]."""
    return list(dict.fromkeys(t.strip()[:100] for t in str(s or "").split(",") if t.strip()))[:20]


def add_daf_rows(conn, books, settings):
    """Daf's own rows for Calibre books it hasn't listed yet ({calibre id: (title, [authors])}), so they
    can go on a shelf at once; the next rebuild fills in the rest."""
    from .library import is_private
    for cid, (title, authors) in books.items():
        conn.execute("INSERT OR IGNORE INTO books (id, kind, title, author, calibre_id, private) VALUES (?, 'book', ?, ?, ?, ?)",
                     (f"cal:{cid}", title or "Unknown", " & ".join(authors or []) or None, int(cid), 1 if is_private(title, settings) else 0))
