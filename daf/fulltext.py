"""The whole article, for a feed item that came as a summary: Daf fetches the page and keeps its
text, the way Read You's "full content" does. trafilatura finds the article in the page; the result
goes into doc_content in Daf's own block shape, so the reader, search (docs_fts), highlights and
Send to Kindle all get the full text.

Feed links come from strangers: only public addresses are fetched, redirects included (the guard
from kindlesend.py). A page behind a robot check (Cloudflare and the like) can't be read this way;
Save to Library can, since Karakeep reads pages with a browser.
"""
import json
import time
import urllib.parse
import urllib.request

from . import content
from .kindlesend import _OPENER, _public

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
MAX_BYTES = 6 * 1024 * 1024
PER_SYNC = 8                     # feeds set to "always": new items fetched per sync run


class FullTextError(Exception):
    pass


def page_blocks(url):
    """The article's blocks from the page at url."""
    u = urllib.parse.urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        raise FullTextError("This item has no web page to read.")
    if not _public(u.hostname):
        raise FullTextError("Daf only reads pages on public addresses.")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        with _OPENER.open(req, timeout=20) as r:
            raw = r.read(MAX_BYTES + 1)
            charset = r.headers.get_content_charset() or "utf-8"
            status = r.status
    except urllib.error.HTTPError as e:
        raise FullTextError(f"The site answered {e.code}.") from e
    except Exception as e:  # noqa: BLE001
        raise FullTextError(f"The site didn't answer: {e}") from e
    if len(raw) > MAX_BYTES:
        raise FullTextError("The page is too big to read.")
    bl = content.article(raw.decode(charset, "replace"), url)
    text = " ".join(b["x"] for b in bl if b["t"] != "img").lower()
    if status == 202 or any(s in text for s in ("verify that you're not a robot", "verify you are human", "enable javascript and cookies")):
        raise FullTextError("The site checks for robots before it shows the page. Save it to the Library: Karakeep reads it with a browser.")
    return bl


def _keep(conn, doc_id, bl):
    conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (doc_id, json.dumps(bl), int(time.time())))
    conn.execute("UPDATE docs SET words = ?, full = 1 WHERE id = ?", (content.words(bl), doc_id))


def load(conn, doc_id):
    """Fetches the full article for a doc and keeps it (Load the full article: the request's own
    connection has written nothing yet while the page is fetched). Returns (words before, words now)."""
    d = conn.execute("SELECT id, url, words FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    bl = page_blocks(d["url"])
    before, now = d["words"] or 0, content.words(bl)
    if now <= max(before, 40):
        raise FullTextError("The page has no more than the feed sent.")
    _keep(conn, doc_id, bl)
    return before, now


def backfill(settings, limit=PER_SYNC):
    """The feeds set to "always load the full article": their new unseen items, a few each sync, three
    pages at a time. Run outside the sync's transaction (sync.loop): the ids are read in one short
    session, the pages fetched with none open, and each result written in a short session of its own,
    so the network never holds the database's write lock."""
    from concurrent.futures import ThreadPoolExecutor
    from . import db
    feeds = [f for f in settings.get("feed_full") or [] if isinstance(f, str)]
    if not feeds:
        return 0
    with db.session() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT id, url, words FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND full IS NULL AND url != '' "
            f"AND feed IN ({','.join('?' * len(feeds))}) ORDER BY added DESC LIMIT ?", (*feeds, limit))]

    def one(r):
        try:
            bl = page_blocks(r["url"])
            return r, bl if content.words(bl) > max(r["words"] or 0, 40) else None
        except Exception:  # noqa: BLE001 - a page that won't give its text stays a summary
            return r, None

    n = 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        for r, bl in pool.map(one, rows):
            with db.session() as c:
                if bl:
                    _keep(c, r["id"], bl)
                    n += 1
                else:
                    c.execute("UPDATE docs SET full = 0 WHERE id = ?", (r["id"],))
    return n
