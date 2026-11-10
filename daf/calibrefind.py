"""Find details: a Calibre book's details and covers as others have them, for the Edit sheet to
compare and take from. Two places are asked at once:

- Calibre's own metadata sources (Google, Amazon.com, Edelweiss, Open Library…), run by Calibre in
  Calibre-Web Automated's container the same way calibrewrite.py runs changes, only reading.
- Hardcover, through Daf's own connection (hardcover.py): its matches for the ISBN, then the title.

Each answer comes back in the shape of the Edit sheet's fields. It takes 10–40 seconds, so it's a
job the page asks about (calibrewrite's jobs)."""
import html
import json
import logging
import re
import subprocess
import threading
import time
import uuid

from . import calibrewrite as W

log = logging.getLogger("daf.calibrefind")
RUN = W.RUN             # Calibre's runtime, for identify(): it reads the web, never the library

IDENTIFY = r'''
def main():
    import json, sys
    from threading import Event
    from calibre.utils.logging import ThreadSafeLog
    from calibre.ebooks.metadata.sources.identify import identify
    from calibre.customize.ui import metadata_plugins
    job = json.loads(sys.stdin.read())
    log = ThreadSafeLog(level=ThreadSafeLog.ERROR)
    out = []
    try:
        res = identify(log, Event(), title=job.get("title") or None, authors=job.get("authors") or None,
                       identifiers=job.get("identifiers") or {}, timeout=job.get("timeout", 25))
        plugins = list(metadata_plugins(["identify"]))
        for r in res[:10]:
            cover, src = None, None
            for p in plugins:
                try:
                    u = p.get_cached_cover_url(r.identifiers)
                except Exception:
                    u = None
                if u and not cover:
                    cover = u
                if not src and any(k in (r.identifiers or {}) for k in (p.name.lower().split(".")[0], p.name.lower().replace(" ", ""))):
                    src = p.name
            out.append({"source": src, "title": r.title, "authors": list(r.authors or []), "publisher": r.publisher,
                        "published": r.pubdate.isoformat()[:10] if r.pubdate and r.pubdate.year > 101 else None,
                        "tags": list(r.tags or []), "comments": r.comments or "", "identifiers": dict(r.identifiers or {}),
                        "languages": list(r.languages or []), "series": r.series, "series_index": r.series_index if r.series else None,
                        "rating": r.rating or None, "cover": cover})
    except Exception as e:
        print("DAFRESULT " + json.dumps({"ok": False, "error": str(e)}))
        return
    print("DAFRESULT " + json.dumps({"ok": True, "results": out}))
main()
'''


def _text(h):
    """Calibre's HTML description → the Edit sheet's text, a blank line between paragraphs."""
    t = re.sub(r"(?i)<br\s*/?>", "\n", h or "")
    t = re.sub(r"(?i)</p>|</div>|</li>|</h\d>", "\n\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", t)).strip()


def calibre_sources(title, authors, identifiers, timeout=25):
    job = json.dumps({"title": title, "authors": authors, "identifiers": identifiers, "timeout": timeout})
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
        title = b["title"]
        out.append({"source": "Hardcover", "title": title, "authors": [c["author"]["name"] for c in cs[:4]],
                    "publisher": (ed.get("publisher") or {}).get("name"), "published": b.get("release_date"),
                    "tags": tags, "comments": (b.get("description") or "").strip(), "identifiers": idents,
                    "languages": [((ed.get("language") or {}).get("code3"))] if (ed.get("language") or {}).get("code3") else [],
                    "series": ser["series"]["name"] if ser else None, "series_index": ser.get("position") if ser else None,
                    "pages": b.get("pages"), "rating": None, "cover": (b.get("image") or {}).get("url")})
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
    for x in (res.get("hardcover") or []) + (res.get("calibre_ids") or []) + (res.get("calibre") or []):
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
