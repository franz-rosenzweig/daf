"""Find details: a Calibre book's details and covers as others have them, for the Edit sheet to
compare and take from. As much as possible it is Calibre's own Download metadata, run by Calibre in
Calibre-Web Automated's container (Daf's own Calibre settings, /config/.daf-calibre), only reading:

- Calibre's search over every metadata source it has on (Google, Amazon.com, and the plugins in Daf's
  Calibre settings: Goodreads, Goodreads More Tags), its answers merged and in Calibre's order, with
  Calibre's built-in sources kept up to date the way the Calibre app keeps them (update_sources, daily).
- Calibre's covers: every cover source (Amazon, Google, Goodreads, Open Library, Apple Books covers…)
  for the chosen answer, downloaded and measured the way Calibre's cover grid shows them, kept a day
  under the settings folder's found/ for the page to show and take.
- Hardcover, through Daf's own connection (hardcover.py), after Calibre's answers.

It takes 10–40 seconds, so it's a job the page asks about (calibrewrite's jobs)."""
import html
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from . import calibrewrite as W

log = logging.getLogger("daf.calibrefind")
RUN = W.RUN             # Calibre's runtime, for identify(): it reads the web, never the library

IDENTIFY = r'''
def main():
    import json, sys
    from threading import Event
    from calibre.utils.logging import ThreadSafeLog
    from calibre.ebooks.metadata.sources.identify import identify
    from calibre.ebooks.metadata.sources.update import patch_plugins
    from calibre.ebooks.metadata.sources.prefs import msprefs
    from calibre.customize.ui import metadata_plugins
    patch_plugins()                                  # Calibre's sources as last updated (update_sources)
    job = json.loads(sys.stdin.read())
    log = ThreadSafeLog(level=ThreadSafeLog.ERROR)
    out = []
    try:
        res = identify(log, Event(), title=job.get("title") or None, authors=job.get("authors") or None,
                       identifiers=job.get("identifiers") or {}, timeout=job.get("timeout", 30),
                       allowed_plugins=set(job["plugins"]) if job.get("plugins") else None)
        prio = msprefs["cover_priorities"]
        plugins = sorted(metadata_plugins(["identify"]), key=lambda p: prio.get(p.name, 1))
        keys = {"goodreads": "Goodreads", "google": "Google", "amazon": "Amazon.com", "edelweiss": "Edelweiss",
                "openlibrary": "Open Library", "isbndb": "ISBNDB", "hardcover": "Hardcover"}
        for r in res[:12]:
            cover = None
            for p in plugins:
                try:
                    u = p.get_cached_cover_url(r.identifiers)
                except Exception:
                    u = None
                if u:
                    cover = u
                    break
            ids = dict(r.identifiers or {})
            srcs = [v for k, v in keys.items() if k in ids]
            out.append({"source": " · ".join(srcs) or "Calibre", "sources": srcs, "title": r.title, "authors": list(r.authors or []), "publisher": r.publisher,
                        "published": r.pubdate.isoformat()[:10] if r.pubdate and r.pubdate.year > 101 else None,
                        "tags": list(r.tags or []), "comments": r.comments or "", "identifiers": ids,
                        "languages": list(r.languages or []), "series": r.series, "series_index": r.series_index if r.series else None,
                        "rating": r.rating or None, "cover": cover})
    except Exception as e:
        print("DAFRESULT " + json.dumps({"ok": False, "error": str(e)}))
        return
    print("DAFRESULT " + json.dumps({"ok": True, "results": out}))
main()
'''

# Calibre's covers for a book: every cover source (best=False, as the cover grid), or the one Calibre
# would pick (best=True, as bulk download). Each image goes to job["dir"] with a small copy for the page.
COVERS = r'''
def main():
    import json, os, sys, time
    from queue import Queue, Empty
    from threading import Event, Thread
    from calibre.utils.logging import ThreadSafeLog
    from calibre.ebooks.metadata.sources.update import patch_plugins
    from calibre.ebooks.metadata.sources.covers import run_download, download_cover
    from calibre.ebooks.metadata.sources.prefs import msprefs
    from calibre.utils.img import image_from_data, scale_image, image_to_data
    patch_plugins()
    job = json.loads(sys.stdin.read())
    log = ThreadSafeLog(level=ThreadSafeLog.ERROR)
    d = job["dir"]
    os.makedirs(d, exist_ok=True)
    got = []
    try:
        kw = dict(title=job.get("title") or None, authors=job.get("authors") or None, identifiers=job.get("identifiers") or {}, timeout=job.get("timeout", 30))
        if job.get("best"):
            r = download_cover(log, **kw)
            got = [r] if r else []
        else:
            q, abort = Queue(), Event()
            t = Thread(target=run_download, args=(log, q, abort), kwargs=kw, daemon=True)
            t.start()
            t.join(kw["timeout"] + 30)
            abort.set()
            while True:
                try:
                    got.append(q.get_nowait())
                except Empty:
                    break
    except Exception as e:
        print("DAFRESULT " + json.dumps({"ok": False, "error": str(e)}))
        return
    prio = msprefs["cover_priorities"]
    got = [g for g in got if g and g[4]]
    got.sort(key=lambda g: (prio.get(g[0].name, 1), -(g[1] or 0) * (g[2] or 0)))
    out = []
    for n, (plugin, w, h, fmt, data) in enumerate(got):
        name = "%s-%d" % (job.get("prefix", "c"), n)
        with open(os.path.join(d, name + "." + (fmt or "jpg")), "wb") as f:
            f.write(data)
        try:
            _w, _h, small = scale_image(data, width=360, height=540, compression_quality=82)
        except Exception:
            small = data
        with open(os.path.join(d, name + ".thumb.jpg"), "wb") as f:
            f.write(small)
        out.append({"name": name, "fmt": fmt or "jpg", "source": plugin.name, "width": w, "height": h})
    print("DAFRESULT " + json.dumps({"ok": True, "covers": out}))
main()
'''

UPDATE = r'''
def main():
    from calibre.ebooks.metadata.sources.update import main as update
    update()
    print("DAFRESULT {\"ok\": true}")
main()
'''


def _text(h):
    """Calibre's HTML description → the Edit sheet's text, a blank line between paragraphs."""
    t = re.sub(r"(?i)<br\s*/?>", "\n", h or "")
    t = re.sub(r"(?i)</p>|</div>|</li>|</h\d>", "\n\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", t)).strip()


def calibre_sources(title, authors, identifiers, timeout=30, plugins=None):
    job = json.dumps({"title": title, "authors": authors, "identifiers": identifiers, "timeout": timeout, "plugins": plugins})
    try:
        r = subprocess.run(RUN + [W.DEBUG, "-c", IDENTIFY], input=job, capture_output=True, text=True, timeout=timeout + 60)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise RuntimeError(f"Calibre's sources didn't answer: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        raise RuntimeError("Calibre's sources didn't answer")
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "Calibre's sources said no")
    for x in out["results"]:
        x["comments"] = _text(x["comments"])
        x["source"] = x["source"] or "Calibre"
    return out["results"]


# Where Calibre leaves the covers it found: the same folder seen from the container and from here.
FOUND_IN = os.environ.get("DAF_CALIBRE_FOUND_IN", "/config/.daf-calibre/found")
FOUND = Path(os.environ.get("DAF_CALIBRE_FOUND", "/srv/docker/cwa/.daf-calibre/found"))


def _run(script, job, timeout):
    try:
        r = subprocess.run(RUN + [W.DEBUG, "-c", script], input=json.dumps(job), capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise RuntimeError(f"Calibre didn't answer: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        raise RuntimeError("Calibre didn't answer")
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        raise RuntimeError(out.get("error") or "Calibre said no")
    return out


def _tidy_found():
    """Covers found more than a day ago go."""
    try:
        for d in FOUND.iterdir():
            if d.is_dir() and time.time() - d.stat().st_mtime > 86400:
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


def calibre_covers(jid, title, authors, identifiers, best=False, prefix="c", timeout=30):
    """Calibre's covers for a book (COVERS) → [{name, fmt, source, width, height}], the files in FOUND/jid."""
    job = {"title": title, "authors": authors, "identifiers": identifiers, "timeout": timeout, "best": best,
           "dir": f"{FOUND_IN}/{jid}", "prefix": prefix}
    return _run(COVERS, job, timeout + 90)["covers"]


def found_file(ref, thumb=False):
    """'jid/name' → the cover's file here, or None."""
    m = re.fullmatch(r"([0-9a-f]{12})/([A-Za-z0-9_-]{1,40})", ref or "")
    if not m:
        return None
    d = FOUND / m.group(1)
    if thumb:
        f = d / f"{m.group(2)}.thumb.jpg"
        return f if f.exists() else None
    return next((f for f in d.glob(m.group(2) + ".*") if not f.name.endswith(".thumb.jpg")), None) if d.is_dir() else None


def covers_start(cid, title, authors, identifiers):
    """Every cover source for this book, as a job: {state, covers}."""
    jid = uuid.uuid4().hex[:12]
    W._jobs[jid] = {"state": "running", "started": time.time(), "id": cid, "kind": "covers", "covers": []}
    _tidy_found()

    def work():
        try:
            W._jobs[jid].update(state="done", covers=calibre_covers(jid, title, authors, identifiers))
        except Exception as e:  # noqa: BLE001
            W._jobs[jid].update(state="failed", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return jid


def update_sources():
    """Calibre's built-in metadata sources, updated from calibre's own server the way the app does it."""
    _run(UPDATE, {}, 300)


HC_BOOK = """query($id:Int!){ books_by_pk(id:$id){ id title subtitle description release_date pages image { url } cached_tags cached_contributors
  book_series { position series { name } }
  default_physical_edition { isbn_13 isbn_10 publisher { name } language { code3 } }
  default_ebook_edition { isbn_13 isbn_10 publisher { name } language { code3 } } } }"""


def hardcover(conn, book_id, q=None, limit=4):
    from . import hardcover as H
    out = []
    for hit in (H.search(conn, q=q) if q else H.search(conn, book_id))[:limit]:
        try:
            b = H.gql(HC_BOOK, {"id": int(hit["id"])})["books_by_pk"]
        except Exception as e:  # noqa: BLE001 - one book Hardcover won't give
            log.info("hardcover book %s: %s", hit.get("id"), e)
            continue
        if not b:
            continue
        out.append(_hc_shape(b))
    return out


def find(conn_factory, cid, book_id, title, authors, identifiers, q=None):
    """Both places at once; whichever fails just says so."""
    res, errs = {}, []

    ids = {k: v for k, v in identifiers.items() if k in ("isbn", "amazon", "google", "goodreads", "edelweiss", "openlibrary")}

    def cal(by_ids):
        # By the book's identifiers, and by its title and author alone: an ISBN in Calibre can be
        # wrong (a study guide's), and then only the title finds the book itself.
        try:
            res["calibre_ids" if by_ids else "calibre"] = calibre_sources(title, authors, ids if by_ids else {})
        except Exception as e:  # noqa: BLE001
            if not by_ids:
                errs.append(f"Calibre's sources: {e}")

    def hc():
        conn = conn_factory()
        try:
            res["hardcover"] = hardcover(conn, book_id, q)
        except Exception as e:  # noqa: BLE001
            errs.append(f"Hardcover: {e}")
        finally:
            conn.close()
    ts = [threading.Thread(target=cal, args=(False,)), threading.Thread(target=hc)] + ([threading.Thread(target=cal, args=(True,))] if ids else [])
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    out, seen = [], set()
    hc = res.get("hardcover") or []
    if not q:
        hc = [x for x in hc if same_book({"title": title, "authors": authors}, x)]
    for x in (res.get("calibre_ids") or []) + (res.get("calibre") or []) + hc:
        key = (x["identifiers"].get("isbn") or x["identifiers"].get("google") or x["identifiers"].get("amazon") or "") + "|" + (x["title"] or "").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return {"results": out, "errors": errs}


def start(conn_factory, cid, book_id, title, authors, identifiers, q=None):
    jid = uuid.uuid4().hex[:12]
    W._jobs[jid] = {"state": "running", "started": time.time(), "id": cid, "kind": "find"}

    def work():
        try:
            W._jobs[jid].update(state="done", **find(conn_factory, cid, book_id, title, authors, identifiers, q))
        except Exception as e:  # noqa: BLE001
            W._jobs[jid].update(state="failed", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return jid



# ---------- Find details for many books: what's missing, from an answer that's surely the same book ----------
FILL_FIELDS = ["publisher", "published", "comments", "tags", "series", "languages", "identifiers", "#pages", "cover"]
QUICK = None            # every source Calibre has on, as its own bulk Download metadata does
_hc_gate = threading.Lock()
_hc_last = [0.0]


def _hc(query, variables):
    """Hardcover, a little over a second apart: it allows 60 questions a minute."""
    from . import hardcover as H
    with _hc_gate:
        wait = 1.1 - (time.time() - _hc_last[0])
        if wait > 0:
            time.sleep(wait)
        _hc_last[0] = time.time()
    return H.gql(query, variables)


def same_book(book, cand):
    """Is this answer surely the book: the same title (subtitles aside) and the same author?"""
    from .library import norm, surname
    a, b = norm(book["title"]), norm(cand.get("title") or "")
    if not a or not b or not (a == b or a.startswith(b + " ") or b.startswith(a + " ")):
        return False
    from .catalog import fold
    who = surname((book.get("authors") or [""])[0])
    return bool(who) and who in re.sub(r"[^a-z]+", " ", fold(" ".join(cand.get("authors") or [])))


def _hardcover_answer(book):
    """Hardcover's book for this one, when it's surely the same: by its Hardcover id, else its ISBN,
    else its title and author."""
    hid = (book["identifiers_map"].get("hardcover-book") or "").strip()
    if not hid.isdigit():
        isbn = re.sub(r"[^0-9Xx]", "", book["identifiers_map"].get("isbn") or "")
        if len(isbn) in (10, 13):
            f = "isbn_13" if len(isbn) == 13 else "isbn_10"
            eds = _hc("query($i:String!){ editions(where:{%s:{_eq:$i}}, limit:1){ book { id } } }" % f, {"i": isbn})["editions"]
            hid = str(eds[0]["book"]["id"]) if eds else ""
    if not hid.isdigit():
        q = f"{book['title'].split(':')[0]} {(book.get('authors') or [''])[0]}".strip()
        hits = (_hc('query($q:String!){ search(query:$q, query_type:"Book", per_page:5, page:1){ results } }', {"q": q})["search"]["results"] or {}).get("hits", [])
        for h in hits:
            d = h["document"]
            if same_book(book, {"title": d.get("title"), "authors": d.get("author_names") or []}):
                hid = str(d["id"])
                break
    if not hid.isdigit():
        return None
    b = _hc(HC_BOOK, {"id": int(hid)})["books_by_pk"]
    if not b:
        return None
    x = _hc_shape(b)
    return x if same_book(book, x) or book["identifiers_map"].get("hardcover-book") == hid else None


def _hc_shape(b):
    ed = b.get("default_physical_edition") or b.get("default_ebook_edition") or {}
    cs = [c for c in (b.get("cached_contributors") or []) if c.get("author") and not c.get("contribution")]
    cs = cs or [c for c in (b.get("cached_contributors") or []) if c.get("author")][:1]
    tags = []
    for kind in ("Genre", "Tag"):
        for t in ((b.get("cached_tags") or {}).get(kind) or [])[:8]:
            name = t.get("tag") if isinstance(t, dict) else t
            if name and name not in tags:
                tags.append(name)
    ser = next((s for s in b.get("book_series") or [] if s.get("series")), None)
    idents = {"hardcover-book": str(b["id"])}
    if ed.get("isbn_13") or ed.get("isbn_10"):
        idents["isbn"] = ed.get("isbn_13") or ed.get("isbn_10")
    return {"source": "Hardcover", "title": b["title"], "authors": [c["author"]["name"] for c in cs[:4]],
            "publisher": (ed.get("publisher") or {}).get("name"), "published": b.get("release_date"),
            "tags": tags, "comments": (b.get("description") or "").strip(), "identifiers": idents,
            "languages": [((ed.get("language") or {}).get("code3"))] if (ed.get("language") or {}).get("code3") else [],
            "series": ser["series"]["name"] if ser else None, "series_index": ser.get("position") if ser else None,
            "pages": b.get("pages"), "cover": (b.get("image") or {}).get("url")}


def proposals(book, answers, fields, custom_keys):
    """What each sure answer would fill in, field by field, the first answer with a value winning."""
    out, src = {}, {}

    def put(k, v, s):
        if k not in out and v not in (None, "", [], {}):
            out[k], src[k] = v, s
    for a in answers:
        s = a["source"]
        if "publisher" in fields and not book.get("publisher"):
            put("publisher", a.get("publisher"), s)
        if "published" in fields and not book.get("published") and a.get("published"):
            put("published", str(a["published"])[:10], s)
        if "comments" in fields and not book.get("comments"):
            put("comments", a.get("comments"), s)
        if "tags" in fields and not book.get("tags"):
            put("tags", a.get("tags"), s)
        if "series" in fields and not book.get("series") and a.get("series"):
            put("series", a["series"], s)
            if "series" in out and src["series"] == s and a.get("series_index") is not None:
                out.setdefault("series_index", a["series_index"])
        if "languages" in fields and not book.get("languages"):
            put("languages", a.get("languages"), s)
        if "#pages" in fields and "#pages" in custom_keys and not book.get("#pages") and a.get("pages"):
            put("#pages", int(a["pages"]), s)
        if "cover" in fields and not book.get("cover"):
            put("cover", a.get("cover"), s)
    if "identifiers" in fields:
        have = dict(book.get("identifiers_map") or {})
        new = {}
        for a in answers:
            for k, v in (a.get("identifiers") or {}).items():
                if k not in have and k not in new and v:
                    new[k] = v
        if new:
            out["identifiers"], src["identifiers"] = new, ", ".join(sorted({a["source"] for a in answers if set(a.get("identifiers") or {}) & set(new)}))
    return out, src


def fill_start(cids, fields):
    from . import catalog
    books, custom_keys = catalog.brief(cids)
    jid = uuid.uuid4().hex[:12]
    job = W._jobs[jid] = {"state": "running", "started": time.time(), "kind": "fill", "done": 0, "total": len(books), "books": []}
    _tidy_found()

    def one(cid):
        b = books[cid]
        answers, errs = [], []
        ids = {k: v for k, v in b["identifiers_map"].items() if k in ("isbn", "google", "amazon", "goodreads", "edelweiss", "openlibrary")}
        try:
            for a in calibre_sources(b["title"], b.get("authors") or [], ids, timeout=30, plugins=QUICK):
                if same_book(b, a):
                    answers.append(a)
        except Exception as e:  # noqa: BLE001
            errs.append(f"Calibre's sources: {e}")
        try:
            hc = _hardcover_answer(b)
            if hc:
                answers.append(hc)
        except Exception as e:  # noqa: BLE001 - one book Hardcover won't give
            errs.append(f"Hardcover: {e}")
        if "cover" in fields and not b.get("cover") and answers:
            # Calibre's own pick of a cover, from every cover source, for the surest answer's identifiers
            try:
                ids2 = dict(ids)
                for a in answers:
                    for k, v in (a.get("identifiers") or {}).items():
                        ids2.setdefault(k, v)
                got = calibre_covers(jid, b["title"], b.get("authors") or [], ids2, best=True, prefix=f"b{cid}")
                if got:
                    answers.insert(0, {"source": got[0]["source"], "cover": f"found:{jid}/{got[0]['name']}"})
            except Exception as e:  # noqa: BLE001
                errs.append(f"Calibre's covers: {e}")
        props, src = proposals(b, answers, fields, custom_keys)
        job["books"].append({"id": cid, "daf_id": b.get("id") or f"cal:{cid}", "title": b["title"], "authors": b.get("authors") or [],
                             "fill": props, "from": src, "found": bool(answers), "errors": errs})
        job["done"] += 1

    def work():
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(one, list(books)))
            order = {c: i for i, c in enumerate(cids)}
            job["books"].sort(key=lambda x: order.get(x["id"], 0))
            job["state"] = "done"
        except Exception as e:  # noqa: BLE001
            job.update(state="failed", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    return jid
