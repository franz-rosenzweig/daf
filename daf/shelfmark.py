"""Shelfmark in Add a book (web/addbook.js), in either of Shelfmark's search modes.

Universal searches book metadata, then the releases for the book you pick. Direct searches releases straight
away, so each result already has its Download button. Shelfmark stays in charge of sources and downloading
into Calibre-Web-Automated's import folder. Source URLs stay on the server: the browser gets a short-lived
id, and download() sends Shelfmark the release it returned for that id.
"""
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import config, freebooks, secrets

_KEPT = {}                 # release id -> (when, Shelfmark's download payload)
KEEP_SECONDS = 60 * 60


class Unavailable(RuntimeError):
    """Shelfmark, or one of its sources, didn't answer."""


def _request(path, params=None, body=None, timeout=60):
    url = config.SHELFMARK_URL.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json", "User-Agent": "Daf/1.0"}
    key = secrets.shelfmark_key()
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read() or b"{}")
        except ValueError:
            err = {}
        if e.code == 401:
            msg = "Shelfmark didn't take its API key (SHELFMARK_API_KEY)"
        else:
            msg = err.get("error") or err.get("message") or f"Shelfmark answered {e.code}"
        raise Unavailable(msg) from e
    except (OSError, ValueError) as e:
        raise Unavailable(f"Shelfmark didn't answer: {e}") from e


def _cover(url):
    """The original web cover, including when Shelfmark gives us its own cached-cover URL."""
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
        encoded = (urllib.parse.parse_qs(parsed.query).get("url") or [""])[0]
        if "/api/covers/" in parsed.path and encoded:
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
            return raw if raw.startswith(("http://", "https://")) else None
        return url if parsed.scheme in ("http", "https") else None
    except (ValueError, UnicodeDecodeError):
        return None


def _extra(release):
    return release.get("extra") if isinstance(release.get("extra"), dict) else {}


def _downloads(release):
    n = _extra(release).get("downloads")
    return n if isinstance(n, (int, float)) else 0


def _prune():
    now = time.time()
    for key, (when, _) in list(_KEPT.items()):
        if now - when > KEEP_SECONDS:
            _KEPT.pop(key, None)
    if len(_KEPT) > 1000:
        for key, _ in sorted(_KEPT.items(), key=lambda p: p[1][0])[:len(_KEPT) - 1000]:
            _KEPT.pop(key, None)


def _remember(payload):
    key = uuid.uuid4().hex
    _KEPT[key] = (time.time(), payload)
    return key


def _mode():
    data = _request("/api/config", timeout=20)
    return data.get("search_mode") if data.get("search_mode") in ("direct", "universal") else "universal"


def search(q):
    """Shelfmark's results, with any copy already in Calibre marked for Open."""
    q = (q or "").strip()[:200]
    if not q:
        return {"mode": "universal", "hits": []}
    mode = _mode()
    if mode == "direct":
        return _direct(q)
    data = _request("/api/metadata/search", {"query": q, "limit": 20, "content_type": "ebook"}, timeout=60)
    hits = []
    for b in data.get("books") or []:
        if not isinstance(b, dict) or not b.get("provider") or b.get("provider_id") in (None, "") or not b.get("title"):
            continue
        authors = b.get("authors") if isinstance(b.get("authors"), list) else []
        hits.append({"provider": str(b["provider"]), "id": str(b["provider_id"]), "title": str(b["title"]),
                     "author": ", ".join(str(a) for a in authors), "year": b.get("publish_year"),
                     "cover": _cover(b.get("cover_url"))})
    freebooks._mark_have(hits)
    return {"mode": mode, "hits": hits}


def _direct(q):
    """Direct mode: each source result is already a release (Shelfmark's searchBooks + direct payload)."""
    data = _request("/api/releases", {"source": "direct_download", "query": q, "content_type": "ebook"}, timeout=180)
    hits = []
    _prune()
    for release in (data.get("releases") or [])[:40]:
        if not isinstance(release, dict) or not release.get("source") or release.get("source_id") in (None, ""):
            continue
        extra = _extra(release)
        author = str(extra.get("author") or "")
        payload = {"source": release["source"], "source_id": release["source_id"], "title": release.get("title") or "Unknown title",
                   "author": author, "year": str(extra.get("year") or ""), "format": release.get("format"),
                   "size": release.get("size"), "downloads": _downloads(release), "preview": _cover(extra.get("preview")),
                   "content_type": "ebook", "language": release.get("language") or extra.get("language"), "search_mode": "direct"}
        payload = {k: v for k, v in payload.items() if v is not None}
        hits.append({"provider": str(release["source"]), "id": str(release["source_id"]),
                     "title": str(release.get("title") or "Unknown title"), "author": author, "year": extra.get("year"),
                     "cover": _cover(extra.get("preview")), "release_id": _remember(payload),
                     "format": release.get("format"), "language": release.get("language") or extra.get("language"),
                     "size": release.get("size"), "source": release.get("indexer") or release.get("source"),
                     "downloads": _downloads(release)})
    hits.sort(key=lambda x: x["downloads"], reverse=True)
    freebooks._mark_have(hits)
    return {"mode": "direct", "hits": hits, "errors": [str(e)[:300] for e in data.get("errors") or []]}


def _payload(book, release, title, author):
    """The same download body Shelfmark's own ReleaseModal builds (releasePayload.ts)."""
    authors = book.get("authors") if isinstance(book.get("authors"), list) else []
    body = {k: release[k] for k in ("source", "source_id", "format", "size", "size_bytes", "download_url",
                                   "protocol", "indexer", "seeders", "language") if release.get(k) is not None}
    body.update({"title": book.get("title") or title or release.get("title") or "",
                 "author": ", ".join(str(a) for a in authors) or author,
                 "year": str(book.get("publish_year") or ""), "downloads": _downloads(release),
                 "extra": _extra(release), "preview": _cover(book.get("cover_url")),
                 "content_type": release.get("content_type") or "ebook",
                 "series_name": book.get("series_name"), "series_position": book.get("series_position"),
                 "subtitle": book.get("subtitle")})
    return {k: v for k, v in body.items() if v is not None}


def releases(provider, book_id, title="", author=""):
    """Universal mode: a book's downloadable releases, with their private source URLs kept here."""
    provider, book_id = (provider or "").strip()[:80], (book_id or "").strip()[:300]
    if not provider or not book_id:
        raise ValueError("Shelfmark needs the book's provider and id")
    data = _request("/api/releases", {"provider": provider, "book_id": book_id, "title": (title or "")[:300],
                                      "author": (author or "")[:300], "content_type": "ebook"}, timeout=180)
    book = data.get("book") if isinstance(data.get("book"), dict) else {}
    _prune()
    out = []
    for release in (data.get("releases") or [])[:80]:
        if not isinstance(release, dict) or not release.get("source") or release.get("source_id") in (None, ""):
            continue
        key = _remember(_payload(book, release, title, author))
        out.append({"id": key, "title": str(release.get("title") or book.get("title") or title),
                    "format": release.get("format"), "language": release.get("language"), "size": release.get("size"),
                    "source": release.get("indexer") or release.get("source"), "seeders": release.get("seeders"),
                    "downloads": _downloads(release)})
    return {"title": book.get("title") or title, "author": ", ".join(str(a) for a in book.get("authors") or []) or author,
            "releases": out, "errors": [str(e)[:300] for e in data.get("errors") or []]}


def download(release_id):
    """Queue the release Shelfmark returned earlier; never take a source URL from the browser."""
    kept = _KEPT.get(release_id or "")
    if not kept or time.time() - kept[0] > KEEP_SECONDS:
        _KEPT.pop(release_id or "", None)
        raise KeyError(release_id)
    return _request("/api/releases/download", body=kept[1], timeout=30)
