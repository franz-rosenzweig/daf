"""Add from ISBN (Calibre's Add books › Add from ISBN): a list of ISBNs, each looked up with Calibre's
own metadata sources (calibrefind.calibre_sources, by its isbn identifier), and the ones I keep added
to Calibre as books without a file, with what was found and its cover (web/isbnadd.js).

Calibre's dialog adds the books with only their ISBN and then downloads their details; here the
looking up comes first, so I see what each ISBN is before anything is added.
"""
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import calibrefind, calibrewrite as W, catalog, importlist


def parse(text):
    """The text → [{token, isbn}] in order, each ISBN once; a token that isn't a valid ISBN has isbn None."""
    out, seen = [], set()
    for tok in re.split(r"[\s,;]+", str(text or "")):
        tok = tok.strip().strip("()[]")
        if not tok or not re.search(r"\d", tok):
            continue
        isbn = importlist.isbn13(tok) if importlist.valid_isbn(tok) else None
        if isbn in seen:
            continue
        if isbn:
            seen.add(isbn)
        out.append({"token": tok[:40], "isbn": isbn})
    return out[:200]


def in_library():
    """{isbn13: (calibre id, title)} for the books Calibre has with an ISBN."""
    books, _custom = catalog.calibre_rows()
    out = {}
    for cid, b in books.items():
        i = importlist.isbn13(b.get("isbn")) if b.get("isbn") else None
        if i:
            out.setdefault(i, (cid, b.get("title")))
    return out


def _found(isbn):
    res = calibrefind.calibre_sources(None, None, {"isbn": isbn}, timeout=25)
    for r in res:
        if r.get("title"):
            ids = dict(r.get("identifiers") or {})
            ids["isbn"] = isbn
            f = {k: r.get(k) for k in ("title", "authors", "publisher", "published", "tags", "comments", "languages",
                                       "series", "series_index", "cover", "source")} | {"identifiers": ids}
            if not f["cover"]:
                f["cover"] = _cover(f)
            return f
    return None


def _cover(f):
    """No cover came with the details: Calibre's cover sources' best one, kept like Find details' covers ('found:job/name')."""
    jid = uuid.uuid4().hex[:12]
    try:
        got = calibrefind.calibre_covers(jid, f["title"], f.get("authors") or [], f["identifiers"], best=True, timeout=20)
    except Exception:  # noqa: BLE001 - no cover is fine
        return None
    return "found:%s/%s" % (jid, got[0]["name"]) if got else None


def lookup_start(text):
    """A job ({state, items, done, total}) looking every ISBN up, three at a time; items fill in as they come."""
    items = parse(text)
    have = in_library()
    for it in items:
        if not it["isbn"]:
            it["state"] = "bad"
        elif it["isbn"] in have:
            it.update(state="have", calibre_id=have[it["isbn"]][0], title=have[it["isbn"]][1])
        else:
            it["state"] = "wait"
    jid = uuid.uuid4().hex[:12]
    todo = [it for it in items if it["state"] == "wait"]
    job = W._jobs[jid] = {"state": "running", "started": time.time(), "kind": "isbn", "items": items, "done": len(items) - len(todo), "total": len(items)}

    def one(it):
        try:
            f = _found(it["isbn"])
            it.update(state="found", found=f) if f else it.update(state="missing")
        except Exception as e:  # noqa: BLE001 - one ISBN's trouble isn't the others'
            it.update(state="missing", error=str(e)[:200])
        job["done"] += 1

    def work():
        with ThreadPoolExecutor(3) as ex:
            list(ex.map(one, todo))
        job["state"] = "done"
    threading.Thread(target=work, daemon=True).start()
    return jid


def clean_book(b, tags=()):
    """One found book from the page → add_empty's book, checked."""
    if not isinstance(b, dict) or not str(b.get("title") or "").strip():
        raise ValueError("A book needs a title")
    isbn = importlist.isbn13(b.get("isbn")) if importlist.valid_isbn(b.get("isbn")) else None
    ids = {str(k).strip().lower()[:40]: str(v).strip()[:200] for k, v in (b.get("identifiers") or {}).items()
           if re.fullmatch(r"[a-z0-9_:-]{1,40}", str(k).strip().lower()) and str(v or "").strip()} if isinstance(b.get("identifiers"), dict) else {}
    if isbn:
        ids["isbn"] = isbn
    out = {"title": str(b["title"]).strip()[:500], "authors": [str(a).strip()[:200] for a in (b.get("authors") or []) if str(a).strip()][:20],
           "identifiers": ids, "tags": list(dict.fromkeys([str(t).strip()[:100] for t in list(b.get("tags") or []) + list(tags) if str(t).strip()]))[:100]}
    if b.get("series"):
        out["series"] = str(b["series"]).strip()[:300]
        try:
            out["series_index"] = float(b.get("series_index")) if b.get("series_index") not in (None, "") else None
        except (TypeError, ValueError):
            out["series_index"] = None
    if b.get("published") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b["published"])):
        out["pubdate"] = str(b["published"])
    fields = {}
    if str(b.get("publisher") or "").strip():
        fields["publisher"] = str(b["publisher"]).strip()[:300]
    langs = [str(x).strip()[:10] for x in (b.get("languages") or []) if re.fullmatch(r"[a-z]{2,3}", str(x).strip())][:5]
    if langs:
        fields["languages"] = langs
    if str(b.get("comments") or "").strip():
        fields["comments"] = catalog.clean_html(str(b["comments"]))[:100000]
    if fields:
        out["fields"] = fields
    return out
