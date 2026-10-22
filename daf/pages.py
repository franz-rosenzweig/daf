"""Saving a web page to the Library by its address: from the browser extension (webapi.py), the
phone's share menu (reader.push_inbox), the Feed's Save (reader.save_to_library) and an export
file of another app (imports.py).

Daf keeps the Library itself (karakeep.mode() "read" or "off"): a save is a dl: row at once, and a
"page" job (media.py) reads the page from the server: its text, title, author, date and picture, which
is kept here too (STATE/thumbs) so it outlives the site. A page that only shows itself to a real
browser (a robot check, a script-only page) is read by the headless Chrome (browser.py). The old
way ("on"), Karakeep keeps the saved copy and reads the page.

Either way the page is read from the server, signed in nowhere, so a page behind a paywall comes out as
its teaser. When the browser sends the page as you see it (the extension does, with `html`), Daf
keeps that text instead: the article is found in it the way fulltext.py finds it in a page it
fetched, and it replaces Daf's copy whenever it has more words. An export that carries the
article's text (Omnivore, Wallabag) gives it the same way.
"""
import hashlib
import io
import json
import re
import secrets
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from . import config, content, reader
from .sources import karakeep

MAX_HTML = 8 * 1024 * 1024
MAX_PAGE = 6 * 1024 * 1024
MAX_PICTURE = 8 * 1024 * 1024
THUMBS = config.STATE / "thumbs"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
ROBOT = ("verify that you're not a robot", "verify you are human", "enable javascript and cookies", "checking your browser",
         "are you a robot", "press & hold to confirm", "just a moment...")


def make_id():
    return "dl:" + secrets.token_hex(8)


def _strip_query(query):
    """The query without utm_* parameters, the rest left exactly as it was."""
    keep = [p for p in query.split("&") if p and not p.split("=", 1)[0].lower().startswith("utm_")]
    return "&".join(keep)


def clean_url(url):
    """What gets saved: no fragment and no utm_* parameters."""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme, p.netloc, p.path, _strip_query(p.query), ""))


def norm_url(url):
    """What gets compared: clean_url, a lower-case host without a default port, no trailing slash."""
    try:
        p = urlsplit((url or "").strip())
        port = p.port
    except ValueError:
        return (url or "").strip()
    scheme = p.scheme.lower()
    host = (p.hostname or "").lower()
    if port and (scheme, port) not in (("http", 80), ("https", 443)):
        host += f":{port}"
    return urlunsplit((scheme, host, p.path.rstrip("/"), _strip_query(p.query), ""))


WHERE_RANK = {"library": 0, "feed": 2}


def find_doc(c, url):
    """The doc saved from this page, if any: one that isn't deleted first, then the Library's copy,
    then one with highlights, then the newest."""
    n = norm_url(url)
    p = urlsplit(n)
    core = (p.netloc + p.path).lower()
    if not core:
        return None
    rows = c.execute("SELECT d.id, d.url, d.where_, d.status, d.deleted, d.title, d.added, "
                     "(SELECT COUNT(*) FROM highlights h WHERE h.book_id = d.id AND h.deleted = 0) AS n "
                     "FROM docs d WHERE d.url IS NOT NULL AND instr(lower(d.url), ?) > 0", (core,)).fetchall()
    rows = [r for r in rows if norm_url(r["url"]) == n]
    if not rows:
        return None
    return min(rows, key=lambda r: (r["status"] == "deleted", WHERE_RANK.get(r["where_"], 1), -r["n"], -(r["added"] or 0)))


def host(url):
    return re.sub(r"^www\.", "", (urlsplit(url).hostname or "").lower())


def save_page(c, url, title=None, added=None):
    """The page's doc, saving it to the Library first if it isn't there, with its row made now so a
    highlight can attach at once. A Feed item is saved to the Library the way Daf's own Save does,
    one deleted a while ago comes back, and an archived one comes back to the top of the Inbox, as
    saving it again does in Karakeep. Returns (doc id, saved). With Karakeep keeping the Library,
    raises karakeep.KarakeepError."""
    d, gone, back = find_doc(c, url), None, False
    own = not karakeep.writes()
    if d and d["status"] == "deleted":
        if d["deleted"] != 1 or own:              # still there (Karakeep's, or Daf's own): Undo, in effect
            reader.set_status(c, d["id"], "unseen" if d["where_"] == "feed" else "inbox")
            back = True
        else:
            gone, d = d["id"], None               # gone from Karakeep: a new save, and its highlights move to it
    if d and d["where_"] == "feed":
        return reader.save_to_library(c, d["id"]), True
    if d:
        if d["where_"] == "library" and d["status"] == "archive" and not added:
            c.execute("UPDATE docs SET status = 'inbox', added = ? WHERE id = ?", (int(time.time()), d["id"]))
            back = True
        return d["id"], back
    url = clean_url(url)
    title = " ".join(str(title or "").split())[:300] or None
    if own:
        new_id_ = make_id()
        c.execute("INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, added) "
                  "VALUES (?, ?, 'library', 'inbox', ?, '', ?, '', ?, ?)",
                  (new_id_, karakeep.kind_of(url, None), title or url, host(url), url, int(added or time.time())))
        from . import media
        media.queue(c, "page", new_id_)
    else:
        b = karakeep.save(url, title)
        if not b.get("id"):
            raise karakeep.KarakeepError("Karakeep didn't say where it put the page")
        new_id_ = "kk:" + b["id"]
        # Karakeep answers with the bookmark it already had for this link, if any: keep Daf's row as it is.
        c.execute("INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, added, ext_id) "
                  "VALUES (?, ?, 'library', 'inbox', ?, '', ?, '', ?, ?, ?) ON CONFLICT(id) DO NOTHING",
                  (new_id_, karakeep.kind_of(url, None), title or url, host(url), url, int(added or time.time()), b["id"]))
    new_id = new_id_
    if gone:
        # Its highlights, reading and vault note go to the new save, so the next highlight adds to
        # the same note instead of starting "Title (2)".
        c.execute("UPDATE highlights SET book_id = ? WHERE book_id = ?", (new_id, gone))
        c.execute("UPDATE sessions SET item = ? WHERE item = ? AND source = 'article'", (new_id, gone))
        c.execute("UPDATE OR IGNORE books SET id = ? WHERE id = ?", (new_id, gone))
        c.execute("DELETE FROM books WHERE id = ?", (gone,))
        c.execute("UPDATE docs SET note = COALESCE(note, (SELECT note FROM docs WHERE id = ?)) WHERE id = ?", (gone, new_id))
        c.execute("DELETE FROM docs WHERE id = ?", (gone,))
    return new_id, True


def article_blocks(html, url=None, whole_page=True):
    """Daf's blocks for a page's HTML. A whole page has its article found in it first; an article's
    own HTML (an export's) goes straight in."""
    return content.article(html, url) if whole_page else content.blocks(html or "")


def keep_text(c, doc_id, html, url=None, whole_page=True):
    """Keeps the page's text for a doc when it has more words than Daf has (a paywalled page saved
    by Karakeep is its teaser). Returns the words kept, or None if Daf's copy was as long."""
    if not html or len(html) > MAX_HTML:
        return None
    try:
        bl = article_blocks(html, url, whole_page)
    except Exception:  # noqa: BLE001 - a page Daf can't read keeps Karakeep's copy
        return None
    n = content.words(bl)
    if n < 40:
        return None
    row = c.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    have = 0
    if row and row[0]:
        try:
            have = content.words(json.loads(row[0]))
        except ValueError:
            have = 0
    if have and n <= have * 1.05:
        return None
    c.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (doc_id, json.dumps(bl), int(time.time())))
    # The summary was made from the teaser, if there was one: a new one comes with the next sync.
    if have:
        c.execute("DELETE FROM jobs WHERE kind = 'summary' AND ref = ? AND status IN ('done', 'failed')", (doc_id,))
    c.execute("UPDATE docs SET words = ?, full = 1, summary = CASE WHEN ? THEN ? ELSE COALESCE(NULLIF(summary, ''), ?) END, "
              "ai_summary = CASE WHEN ? THEN NULL ELSE ai_summary END WHERE id = ?",
              (n, have > 0, content.summary(bl), content.summary(bl), have > 0, doc_id))
    return n


# ---- Daf reads the page itself -------------------------------------------------------------------

def _get(url, limit=MAX_PAGE, accept="text/html,application/xhtml+xml,*/*;q=0.8"):
    """(bytes, content type, the address it ended on, status) from a public address."""
    from .kindlesend import _OPENER, _public
    u = urlsplit(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("not a web address")
    if not _public(u.hostname):
        raise ValueError("Daf only reads pages on public addresses")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en,he;q=0.8"})
    with _OPENER.open(req, timeout=20) as r:
        raw = r.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("too big")
        return raw, (r.headers.get("Content-Type") or "").lower(), r.geturl(), r.status


def _html(raw, ctype):
    m = re.search(r"charset=([\w-]+)", ctype or "")
    try:
        return raw.decode(m.group(1) if m else "utf-8", "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _robot(html, status=200):
    t = (html or "")[:200_000].lower()
    return status in (202, 403, 429, 503) or any(s in t for s in ROBOT)


def keep_thumb(img_url):
    """The page's picture, kept on the server (STATE/thumbs, at most 960 px): its address in Daf, or None."""
    try:
        raw, ctype, _, _ = _get(img_url, MAX_PICTURE, "image/avif,image/webp,image/*,*/*;q=0.5")
    except Exception:  # noqa: BLE001 - no picture is fine
        return None
    return keep_thumb_bytes(raw)


def keep_thumb_bytes(raw):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        im.thumbnail((960, 960))
        if im.mode not in ("RGB", "L"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
            im = bg
        if im.width < 40 or im.height < 40:
            return None                           # a tracking pixel or an icon
        out = io.BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
    except Exception:  # noqa: BLE001
        return None
    data = out.getvalue()
    name = hashlib.sha1(data).hexdigest()[:16] + ".jpg"
    THUMBS.mkdir(parents=True, exist_ok=True)
    f = THUMBS / name
    if not f.exists():
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(f)
    return "/api/thumb/" + name


def _looks_like_address(t):
    return not t or bool(re.match(r"^(https?://|www\.)", t.strip()))


def _trim(bl):
    """A run of pictures before the first words is the site's menu (Paul Graham's, as images), not the article."""
    i = 0
    while i < len(bl) and bl[i].get("t") == "img":
        i += 1
    return bl[i:] if i >= 3 else bl


def fetch(conn, doc_id):
    """The "page" job: reads a saved page and keeps its text (when it has more than Daf's copy), its
    title, author and date when Daf has none, and its picture. Commits as it goes, so the page's
    reading isn't held up by a slow site."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d or not d["url"] or d["status"] == "deleted":
        return
    url, kind = d["url"], d["kind"]
    html, final, status, raw, ctype = None, url, 200, None, ""
    try:
        raw, ctype, final, status = _get(url)
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:  # noqa: BLE001 - the browser may still read it
        pass
    if raw is not None and ("application/pdf" in ctype or raw[:5] == b"%PDF-"):
        from . import media, pdfdoc
        pdfdoc.DIR.mkdir(parents=True, exist_ok=True)
        pdfdoc.path_for(doc_id).write_bytes(raw)
        conn.execute("UPDATE docs SET kind = 'pdf' WHERE id = ?", (doc_id,))
        media.queue(conn, "pdf", doc_id)
        return
    if raw is not None:
        html = _html(raw, ctype)
    bl = _trim(article_blocks(html, final)) if html and kind in ("article", "tweet") else []
    if kind in ("article", "tweet") and (not html or _robot(html, status) or content.words(bl) < 80):
        from . import browser
        try:
            h2, f2 = browser.page_html(url)
            b2 = _trim(article_blocks(h2, f2))
            if h2 and (not html or content.words(b2) > content.words(bl) or _robot(html, status)):
                html, final, bl = h2, f2, b2
        except Exception:  # noqa: BLE001 - what the plain fetch got stays
            pass
    if not html:
        raise RuntimeError(f"the site didn't give the page ({status})")
    meta = None
    try:
        import trafilatura
        meta = trafilatura.extract_metadata(html, default_url=final)
    except Exception:  # noqa: BLE001
        meta = None
    m = meta.as_dict() if meta else {}
    sets, args = [], []
    if (m.get("title") or "").strip() and (_looks_like_address(d["title"]) or d["title"] == url):
        sets.append("title = ?"); args.append(" ".join(m["title"].split())[:300])
    if (m.get("author") or "").strip() and not (d["author"] or "").strip():
        sets.append("author = ?"); args.append(m["author"][:200])
    if m.get("sitename") and (not d["source"] or d["source"] == host(url)) and m["sitename"] != host(final):
        sets.append("source = ?"); args.append(m["sitename"][:120])
    if m.get("date") and not d["published"]:
        try:
            from datetime import datetime
            sets.append("published = ?"); args.append(int(datetime.fromisoformat(m["date"]).timestamp()))
        except ValueError:
            pass
    if (m.get("description") or "").strip() and not (d["summary"] or "").strip():
        sets.append("summary = ?"); args.append(m["description"].strip()[:280])
    if sets:
        conn.execute(f"UPDATE docs SET {', '.join(sets)} WHERE id = ?", (*args, doc_id))
    conn.commit()
    if bl and content.words(bl) >= 40 and not _robot(html):
        row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
        have = content.words(json.loads(row[0])) if row and row[0] else 0
        if content.words(bl) > have * 1.05:
            conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (doc_id, json.dumps(bl), int(time.time())))
            conn.execute("UPDATE docs SET words = ?, summary = COALESCE(NULLIF(summary, ''), ?) WHERE id = ?",
                         (content.words(bl), content.summary(bl), doc_id))
            conn.commit()
    if m.get("image") and (not d["thumb"] or str(d["thumb"]).startswith("http")):
        t = keep_thumb(m["image"])
        if t:
            conn.execute("UPDATE docs SET thumb = ? WHERE id = ?", (t, doc_id))
    from . import ai
    if ai.settings().get("auto_tags", True):
        from . import media
        media.queue(conn, "tags", doc_id)
