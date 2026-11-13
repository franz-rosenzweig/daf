"""Public-domain books (web/addbook.js: Add a book → Public domain): Standard Ebooks' and Project
Gutenberg's own searches, and a book from either straight into Calibre through Calibre-Web-Automated's
import folder, the way a dropped EPUB goes (then Books, readable in Daf, sendable to the Kindle).

Only these two sites' own EPUBs are fetched, one book at a time when it's asked for: the page names a
book by its source and id, never by a link. Standard Ebooks first, since their editions are proofread
and typeset; a Gutenberg result that's the same book is left out."""
import concurrent.futures
import html
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config

UA = "Daf/1.0 (personal reading app)"
SE = "https://standardebooks.org"
PG = "https://www.gutenberg.org"
MAX_BYTES = 100 * 1024 * 1024
SE_ID = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+){1,4}$")
ATOM = "{http://www.w3.org/2005/Atom}"


class Exists(Exception):
    def __init__(self, msg, book_id=None):
        super().__init__(msg)
        self.book_id = book_id


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("That file is over 100 MB")
        return data


def _text(s):
    return html.unescape(re.sub(r"\s+", " ", s or "")).strip()


def search_se(q, n=12):
    s = _get(f"{SE}/ebooks?" + urllib.parse.urlencode({"query": q, "per-page": 24})).decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<li typeof="schema:Book" about="/ebooks/([^"]+)">(.*?)</li>', s, re.S):
        path, body = m.group(1), m.group(2)
        if not SE_ID.match(path):
            continue
        t = re.search(r'<p><a [^>]*property="schema:url"><span property="schema:name">([^<]+)</span>', body)
        authors = re.findall(r'class="author"[^>]*>\s*<a [^>]*><span property="schema:name">([^<]+)</span>', body)
        img = re.search(r'<img src="([^"]+)"', body)
        if not t:
            continue
        out.append({"source": "se", "id": path, "title": _text(t.group(1)), "author": ", ".join(_text(a) for a in authors),
                    "cover": SE + img.group(1) if img and img.group(1).startswith("/") else None})
        if len(out) >= n:
            break
    return out


def search_pg(q, n=15):
    root = ET.fromstring(_get(f"{PG}/ebooks/search.opds/?" + urllib.parse.urlencode({"query": q})))
    out = []
    for e in root.iter(ATOM + "entry"):
        m = re.search(r"/ebooks/(\d+)\.opds$", e.findtext(ATOM + "id") or "")
        if not m:
            continue
        num = m.group(1)
        out.append({"source": "pg", "id": num, "title": _text(e.findtext(ATOM + "title")), "author": _text(e.findtext(ATOM + "content")),
                    "cover": f"{PG}/cache/epub/{num}/pg{num}.cover.medium.jpg"})
        if len(out) >= n:
            break
    return out


def _key(title, author):
    t = re.sub(r"[^a-z0-9 ]", "", (title or "").lower().split(":")[0]).strip()
    words = re.findall(r"[a-z]+", (author or "").lower())
    return t, (words[-1] if words else "")


_CACHE = {}          # (site, query) -> (when, results): Standard Ebooks' search takes seconds on their side


def _cached(site, q, fn):
    k = (site, q.lower())
    hit = _CACHE.get(k)
    if hit and time.time() - hit[0] < 600:
        return [dict(x) for x in hit[1]]
    r = fn(q)
    if len(_CACHE) > 200:
        _CACHE.clear()
    _CACHE[k] = (time.time(), r)
    return [dict(x) for x in r]


def search(q, site=None):
    """One site's results (site: se or pg), or both at once. → {"results": [...], "failed": [names]}.
    Each result has `key` (the same book on both sites shares it) and `rank` (0: every asked-for word
    in the title … 3: none in title or author), so the page can put the two together as they come."""
    q = (q or "").strip()[:200]
    if not q:
        return {"results": [], "failed": []}
    sites = {"se": ("Standard Ebooks", search_se), "pg": ("Project Gutenberg", search_pg)}
    want = [site] if site in sites else list(sites)
    got, failed = {}, []
    with concurrent.futures.ThreadPoolExecutor(len(want)) as ex:
        jobs = {ex.submit(_cached, k, q, sites[k][1]): k for k in want}
        for f in concurrent.futures.as_completed(jobs):
            try:
                got[jobs[f]] = f.result()
            except Exception:  # noqa: BLE001 - one site down still shows the other's
                failed.append(sites[jobs[f]][0])
    words = re.findall(r"\w+", q.lower())

    def rank(x):
        t, a = x["title"].lower(), x["author"].lower()
        return 0 if words and all(w in t for w in words) else 1 if any(w in t for w in words) else 2 if any(w in a for w in words) else 3
    se, pg = got.get("se", []), got.get("pg", [])
    seen = {_key(x["title"], x["author"]) for x in se}
    results = se + [x for x in pg if _key(x["title"], x["author"]) not in seen]
    for x in results:
        x["key"] = "|".join(_key(x["title"], x["author"]))
        x["rank"] = rank(x)
    results.sort(key=lambda x: x["rank"])
    _mark_have(results)
    return {"results": results, "failed": failed}


def _mark_have(results):
    """Each result Calibre has already: its Daf book id as `have`."""
    from . import library
    try:
        books = library.calibre_books()
        m = library.Matcher(books, [])
    except Exception:  # noqa: BLE001 - Calibre unreadable: nothing marked
        return
    for x in results:
        c = m.calibre(x["title"], x["author"])
        x["have"] = f"cal:{c['id']}" if c and x["author"] and library.surname(x["author"]) in (c["author"] or "").lower() else None


def _url(source, book_id):
    if source == "se" and SE_ID.match(book_id or ""):
        return f"{SE}/ebooks/{book_id}/downloads/{book_id.replace('/', '_')}.epub?source=download"
    if source == "pg" and re.fullmatch(r"\d{1,7}", book_id or ""):
        return f"{PG}/ebooks/{book_id}.epub3.images"
    raise ValueError("Not a public-domain book Daf knows")


def _safe(s):
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", s or "").strip().strip(".")
    return re.sub(r"\s+", " ", s)[:120] or "Book"


def add(conn, source, book_id, title="", author="", force=False):
    """One book's EPUB into Calibre-Web-Automated's import folder. → the name it went under. Raises
    Exists when Calibre has the book already (force sends it anyway)."""
    url = _url(source, book_id)
    if not force and title:
        from . import bookfiles
        c = bookfiles.in_calibre(conn, title=title, author=author or None)
        if c:
            raise Exists(f"Calibre has it already: {c['title']}", f"cal:{c['id']}")
    raw = _get(url, timeout=90)
    if not raw.startswith(b"PK"):
        raise ValueError("That wasn't an EPUB")
    config.CWA_INGEST.mkdir(parents=True, exist_ok=True)
    stem = _safe(f"{title} - {author}" if title and author else title or f"{source}-{book_id.replace('/', '-')}")
    dest, n = config.CWA_INGEST / f"{stem}.epub", 2
    while dest.exists():
        dest, n = config.CWA_INGEST / f"{stem} ({n}).epub", n + 1
    part = dest.with_name("." + dest.name + ".part")          # hidden until whole: the import skips it
    part.write_bytes(raw)
    part.replace(dest)
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (f"free:{source}:{book_id}", str(int(time.time()))))
    return dest.name
