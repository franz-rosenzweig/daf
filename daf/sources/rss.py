"""The Feed, fetched by Daf itself, instead of FreshRSS.

The feeds Daf follows live in the table feeds, each with its folder. Every sync reads the ones that
are due (half an hour apart by default) with the conditional GET a polite reader sends (ETag,
Last-Modified), parses them with feedparser, and keeps each new post as a doc with where='feed',
just as FreshRSS's posts were kept (freshrss.sync). Which posts a feed has given is kept in
feed_seen, so a post read and forgotten never comes back. Each feed's icon is kept in feed-icons/,
and each post's own picture, where it has one, in thumbs/ like the Library's (keep_pictures, after
the sync).

This module has the same functions as sources/freshrss.py, and feedsrc.py picks the one in charge
(settings.feed_reader = "daf"), so the rest of Daf doesn't care which it is. Read and starred are
Daf's own here, so marking them changes nothing elsewhere.

The move from FreshRSS (import_freshrss): its feeds come over with their ids ("feed/12", which the
posts already carry), folders, names, icons and the few settings Daf honours (mark new posts read,
a longer timeout, no certificate check), and every post FreshRSS has already brought counts as
seen, by its link, so nothing comes twice.
"""
import calendar
import hashlib
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .. import config, content

UA = "Mozilla/5.0 (compatible; Daf feed reader; +https://github.com/franz-rosenzweig/daf)"
EVERY = 1800                     # seconds between two reads of one feed
ICONS = config.STATE / "feed-icons"
PICTURE_MIN = 100                # px on each side: a smaller picture in a post is an avatar, an emoji or a button
PICTURE_MAX = 640                # a post's picture as kept: enough for its row, and for the Library's card once saved
PICTURES_PER_SYNC = 120


class FeedError(Exception):
    pass


def _conn(conn):
    if conn is not None:
        return conn, False
    from .. import db
    return db.connect(), True


def _done(conn, mine):
    if mine:
        conn.commit()
        conn.close()


# The pool: feeds Daf reads only for the Edition (edition.py), kept out of the Feed. A feed is in it when its
# folder starts with POOL ("Pool · Science"); its posts are stored with where_ = 'pool', so no Feed list,
# count, reader app or digest sees them, it's read less often, and its posts go after POOL_DAYS unless an
# Edition took them (they become ordinary Feed posts then: edition._materialize).
POOL = "Pool · "
POOL_EVERY = 4 * 3600
POOL_DAYS = 5


def is_pool(folder):
    return (folder or "").startswith(POOL)


def _icon_key(feed_id):
    return hashlib.sha1(feed_id.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- what's followed

def subscriptions(conn=None, pool=False):
    """The feeds Daf follows: [{id ("feed/12"), title, folder, url, site, icon}], as freshrss.subscriptions.
    The Edition's pool only with pool=True."""
    conn, mine = _conn(conn)
    try:
        out = []
        for r in conn.execute("SELECT * FROM feeds ORDER BY lower(title)"):
            if is_pool(r["folder"]) and not pool:
                continue
            h = r["icon"] or ""
            out.append({"id": r["id"], "title": r["title"] or r["url"], "folder": r["folder"] or "", "url": r["url"],
                        "site": r["site"] or "", "icon": h if h and any(ICONS.glob(h + ".*")) else "",
                        "error": r["error"], "fetched": r["fetched"]})
        return out
    finally:
        _done(conn, mine)


def folders(conn=None):
    conn, mine = _conn(conn)
    try:
        return sorted({r[0] for r in conn.execute("SELECT DISTINCT folder FROM feeds WHERE folder != ''") if not is_pool(r[0])}, key=str.casefold)
    finally:
        _done(conn, mine)


class _Https(urllib.request.HTTPRedirectHandler):
    """A redirect to plain http is followed over https: plenty of networks don't let port 80 out,
    and the feeds that send you there serve https too (Chrome Releases → feeds.feedburner.com)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl.startswith("http://"):
            newurl = "https://" + newurl[7:]
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url, headers=None, timeout=25, verify=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5", **(headers or {})})
    ctx = None if verify else ssl._create_unverified_context()  # noqa: SLF001 - a feed set to skip the certificate check
    opener = urllib.request.build_opener(_Https, urllib.request.HTTPSHandler(context=ctx))
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.URLError as e:
        if isinstance(e, urllib.error.HTTPError) or not url.startswith("http://"):
            raise
        req.full_url = "https://" + url[7:]          # a plain http feed: its https address, the same way
        return opener.open(req, timeout=timeout)


def _parse(data, ctype=""):
    import feedparser
    d = feedparser.parse(data, response_headers={"content-type": ctype or "application/xml"})
    return d if (d.get("version") or d.entries) else None


class _Links(__import__("html.parser").parser.HTMLParser):
    """A page's <link rel="alternate" type="…rss/atom…">s and its icon."""
    def __init__(self):
        super().__init__()
        self.feeds, self.icon = [], None

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower().split()
        if "alternate" in rel and re.search(r"(rss|atom|feed)\+?xml|application/feed\+json", a.get("type", "").lower()) and a.get("href"):
            self.feeds.append(a["href"])
        if "icon" in rel and a.get("href") and not self.icon:
            self.icon = a["href"]


def discover(url):
    """The feed at url, or the one a site's page names: (feed url, parsed feed, the site's icon link)."""
    try:
        with _get(url) as r:
            data, ctype, final = r.read(5_000_000), r.headers.get("Content-Type", ""), r.geturl()
    except urllib.error.HTTPError as e:
        raise ValueError(f"The site answered {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Couldn't reach it: {e}") from e
    d = _parse(data, ctype)
    if d and d.entries is not None and "html" not in ctype.lower():
        return final, d, None
    p = _Links()
    try:
        p.feed(data.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        pass
    for href in p.feeds:
        f = urllib.parse.urljoin(final, html.unescape(href))
        try:
            with _get(f) as r:
                d = _parse(r.read(5_000_000), r.headers.get("Content-Type", ""))
            if d:
                return f, d, urllib.parse.urljoin(final, p.icon) if p.icon else None
        except Exception:  # noqa: BLE001
            continue
    raise ValueError("There's no feed there")


def _save_icon(key, url):
    """A feed's icon, kept in the state folder as feed-icons/<key>.<ext>."""
    try:
        with _get(url, timeout=10) as r:
            data, ctype = r.read(300_000), r.headers.get("Content-Type", "")
    except Exception:  # noqa: BLE001
        return False
    if not data or not ctype.startswith("image/"):
        return False
    ext = {"image/png": "png", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/svg+xml": "svg",
           "image/gif": "gif", "image/jpeg": "jpg", "image/webp": "webp"}.get(ctype.split(";")[0].strip(), "ico")
    ICONS.mkdir(parents=True, exist_ok=True)
    for old in ICONS.glob(key + ".*"):
        old.unlink()
    (ICONS / f"{key}.{ext}").write_bytes(data)
    return True


def icon(h):
    """A feed's icon as (bytes, type), as freshrss.icon."""
    if not re.fullmatch(r"[0-9a-f]{6,40}", h or ""):
        raise FileNotFoundError(h)
    f = next(ICONS.glob(h + ".*"), None)
    if not f:
        raise FileNotFoundError(h)
    return f.read_bytes(), {"svg": "image/svg+xml", "png": "image/png", "gif": "image/gif", "jpg": "image/jpeg",
                            "webp": "image/webp"}.get(f.suffix[1:], "image/x-icon")


def subscribe(url, folder=None, conn=None):
    """Follow a site or a feed (the feed a site's page names), in a folder. Returns its title."""
    return follow(url, folder, conn)[1]


def follow(url, folder=None, conn=None):
    """subscribe, returning (its id, its title, the feed's address): the reader apps' quickadd wants all three."""
    feed_url, d, icon_url = discover(url)
    conn, mine = _conn(conn)
    try:
        have = conn.execute("SELECT id, title FROM feeds WHERE url = ?", (feed_url,)).fetchone()
        if have:
            if folder is not None:
                conn.execute("UPDATE feeds SET folder = ? WHERE id = ?", (folder or "", have["id"]))
            return have["id"], have["title"], feed_url
        n = 1 + max([int(r[0].split("/", 1)[1]) for r in conn.execute("SELECT id FROM feeds WHERE id LIKE 'feed/%'")
                     if r[0].split("/", 1)[1].isdigit()] or [0])
        fid = f"feed/{n}"
        title = (d.feed.get("title") or urllib.parse.urlparse(feed_url).netloc).strip()[:200]
        site = d.feed.get("link") or ""
        key = _icon_key(fid)
        # its icon: the page's, the feed's own, or the site's favicon.ico
        tries = [icon_url, d.feed.get("icon"), (d.feed.get("image") or {}).get("href"), urllib.parse.urljoin(site, "/favicon.ico") if site else None]
        got = any(_save_icon(key, u) for u in tries if u)
        conn.execute("INSERT INTO feeds (id, url, title, site, folder, icon, added, every) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (fid, feed_url, title, site, folder or "", key if got else None, int(time.time()), POOL_EVERY if is_pool(folder) else None))
        _take(conn, config.load_settings(), dict(conn.execute("SELECT * FROM feeds WHERE id = ?", (fid,)).fetchone()), d)
        conn.execute("UPDATE feeds SET fetched = ?, ok = ? WHERE id = ?", (int(time.time()), int(time.time()), fid))
        return fid, title, feed_url
    finally:
        _done(conn, mine)


def edit_subscription(stream, title=None, folder=None, old_folder=None, conn=None):
    """Rename a feed, or move it to another folder ("" for none)."""
    conn, mine = _conn(conn)
    try:
        if title:
            conn.execute("UPDATE feeds SET title = ? WHERE id = ?", (title, stream))
        if folder is not None:
            conn.execute("UPDATE feeds SET folder = ? WHERE id = ?", (folder, stream))
    finally:
        _done(conn, mine)


def unsubscribe(stream, conn=None):
    conn, mine = _conn(conn)
    try:
        conn.execute("DELETE FROM feeds WHERE id = ?", (stream,))
        conn.execute("DELETE FROM feed_seen WHERE feed = ?", (stream,))
    finally:
        _done(conn, mine)


# Read and starred are Daf's own here: nothing else to tell.
def mark_read(item_ids, read=True):
    return None


def star(item_ids, on=True):
    return None


def mark_all_read_before(ts):
    return None


def unread_counts(conn=None):
    conn, mine = _conn(conn)
    try:
        rows = conn.execute("SELECT category, COUNT(*) FROM docs WHERE where_ = 'feed' AND status = 'unseen' GROUP BY category").fetchall()
        return sum(r[1] for r in rows), {r[0] or "": r[1] for r in rows if r[0]}
    finally:
        _done(conn, mine)


# ---------------------------------------------------------------- reading the feeds

def _fetch(f):
    """One feed read, off the database: (feed row, status, parsed feed or None, etag, modified, error)."""
    attrs = json.loads(f["attrs"] or "{}")
    headers = {}
    if f.get("etag"):
        headers["If-None-Match"] = f["etag"]
    if f.get("modified"):
        headers["If-Modified-Since"] = f["modified"]
    try:
        with _get(f["url"], headers, timeout=int(attrs.get("timeout") or 25), verify=attrs.get("ssl_verify", True) is not False) as r:
            data, ctype = r.read(20_000_000), r.headers.get("Content-Type", "")
            etag, modified = r.headers.get("ETag"), r.headers.get("Last-Modified")
        d = _parse(data, ctype)
        if not d:
            return f, 200, None, etag, modified, "Not a feed any more"
        return f, 200, d, etag, modified, None
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return f, 304, None, f.get("etag"), f.get("modified"), None
        return f, e.code, None, None, None, f"The site answered {e.code}"
    except Exception as e:  # noqa: BLE001
        return f, 0, None, None, None, str(e)[:200] or e.__class__.__name__


def _when(e):
    t = e.get("published_parsed") or e.get("updated_parsed")      # feedparser gives them in UTC
    return calendar.timegm(t) if t else None


def _kind(e, link):
    for enc in e.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("audio/"):
            return "podcast", enc.get("href")
    if "youtube.com/watch" in link or "youtu.be/" in link:
        return "video", None
    return "article", None


def _px(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _picture(e):
    """The address of the post's own picture, where the feed names one: its media:thumbnail (the
    biggest), an image in media:content, an image enclosure or its itunes:image. One the feed says is
    small (GitHub's 30 px avatars) doesn't count. None when it names none: keep_pictures looks in
    the post's text."""
    def ok(url, w=None, h=None):
        url = str(url or "").strip()
        return url.startswith(("http://", "https://")) and not (_px(w) and _px(h) and min(_px(w), _px(h)) < PICTURE_MIN)
    for t in sorted(e.get("media_thumbnail") or [], key=lambda t: -_px(t.get("width"))):
        if ok(t.get("url"), t.get("width"), t.get("height")):
            return t["url"].strip()
    for m in e.get("media_content") or []:
        if (m.get("medium") == "image" or str(m.get("type", "")).startswith("image/")) and ok(m.get("url"), m.get("width"), m.get("height")):
            return m["url"].strip()
    for enc in e.get("enclosures") or []:
        if str(enc.get("type", "")).startswith("image/") and ok(enc.get("href")):
            return enc["href"].strip()
    it = e.get("image") or {}
    return it["href"].strip() if isinstance(it, dict) and ok(it.get("href")) else None


def _take(conn, settings, f, d, pictures=False):
    """A parsed feed's new posts into the Feed. Returns how many were new. With pictures, the posts
    already in the Feed get the picture their feed names for them too (sync does it once)."""
    expire = int(settings.get("feed_expire_days", 30))
    horizon = int(time.time()) - (expire + 2) * 86400
    attrs = json.loads(f.get("attrs") or "{}")
    seen_now = bool(attrs.get("read_upon_reception"))
    where = "pool" if is_pool(f.get("folder")) else "feed"
    now, new = int(time.time()), 0
    for e in d.entries:
        link = (e.get("link") or "").strip()
        key = (e.get("id") or link or e.get("title") or "").strip()[:500]
        if not key:
            continue
        keys = [("id:" + key)] + ([("link:" + link)] if link else [])
        if any(conn.execute("SELECT 1 FROM feed_seen WHERE feed = ? AND key = ?", (f["id"], k)).fetchone() for k in keys):
            pic = _picture(e) if pictures and link else None
            if pic:
                conn.execute("UPDATE docs SET thumb = ? WHERE where_ = 'feed' AND feed = ? AND url = ? AND (thumb IS NULL OR thumb = '')",
                             (pic, f["id"], link))
            continue
        conn.executemany("INSERT OR IGNORE INTO feed_seen (feed, key, at) VALUES (?, ?, ?)", [(f["id"], k, now) for k in keys])
        published = _when(e) or now
        if published < horizon:
            continue
        raw = ((e.get("content") or [{}])[0].get("value") or e.get("summary") or "")
        bl = content.blocks(raw)
        kind, enclosure = _kind(e, link)
        author = (e.get("author") or "").strip()
        did = "rss:" + hashlib.sha1(f"{f['id']}|{key}".encode()).hexdigest()[:16]
        # thumb: the picture's address for now; keep_pictures keeps it on the server after the sync
        conn.execute(
            "INSERT OR IGNORE INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, "
            "words, summary, enclosure, ext_id, feed, thumb) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (did, kind, where, "seen" if seen_now else "unseen", html.unescape(e.get("title") or "Untitled").strip()[:500],
             "" if "@" in author else author[:120], f.get("title") or "", f.get("folder") or "", link, published, now,
             content.words(bl), content.summary(bl), enclosure, key[:300], f["id"], _picture(e)))
        conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (did, json.dumps(bl), now))
        new += 1
    return new


def sync(conn, settings, max_items=1500, every=None, force=False):
    """Read the feeds that are due (all of them with force), keep their new posts. Returns (new, unread)."""
    now = int(time.time())
    every = every or EVERY
    # Once, the first time Daf looks for the posts' pictures: every feed is read afresh (no ETag), so the
    # posts the Feed already has get the picture their feed names, not only one from their text.
    first = not conn.execute("SELECT 1 FROM kv WHERE k = 'feed_pictures'").fetchone()
    due = [dict(r) for r in conn.execute("SELECT * FROM feeds")
           if force or first or not r["fetched"] or now - r["fetched"] >= (r["every"] or every)]
    if first:
        for f in due:
            f["etag"] = f["modified"] = None
    new = 0
    with ThreadPoolExecutor(8) as pool:
        for f, status, d, etag, modified, err in pool.map(_fetch, due):
            if d is not None:
                try:
                    new += _take(conn, settings, f, d, pictures=first)
                except Exception as e:  # noqa: BLE001
                    err = f"Couldn't read its posts: {e}"[:200]
            conn.execute("UPDATE feeds SET fetched = ?, etag = ?, modified = ?, error = ?, errors = ?, ok = COALESCE(?, ok) WHERE id = ?",
                         (now, etag, modified, err, (f.get("errors") or 0) + 1 if err else 0, None if err else now, f["id"]))
            if new >= max_items:
                break
    if first:
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_pictures', '1')")
    total, labels = unread_counts(conn)
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_counts', ?)", (json.dumps({"total": total, "labels": labels}),))
    _forget(conn, settings)
    return new, total


def keep_pictures(limit=PICTURES_PER_SYNC):
    """The posts' own pictures, kept on the server the way the Library's are (pages.keep_thumb), so a
    row shows its post's picture without asking the site each time. Newest first, a few each sync: the
    picture the feed named (_take leaves its address in thumb), else the first big enough picture in
    the post's text, which is how a post from before this gets one when its feed doesn't list it any
    more. A post with none gets thumb '' and isn't looked at again. Run outside the sync's transaction
    (sync.loop), as fulltext.backfill is: the pictures are fetched with no session open."""
    from .. import db, pages
    with db.session() as c:
        rows = [tuple(r) for r in c.execute(
            "SELECT d.id, d.thumb, t.blocks FROM docs d LEFT JOIN doc_content t ON t.id = d.id WHERE d.where_ = 'feed' "
            "AND d.status != 'deleted' AND (d.thumb IS NULL OR d.thumb LIKE 'http%') ORDER BY d.added DESC LIMIT ?", (limit,))]

    def one(r):
        did, named, blocks = r
        try:
            inside = [b["src"] for b in json.loads(blocks or "[]") if b.get("t") == "img"]
        except ValueError:
            inside = []
        for url in list(dict.fromkeys(([named] if named else []) + inside))[:3]:     # three tries at most
            kept = pages.keep_thumb(url, PICTURE_MIN, PICTURE_MAX)
            if kept:
                return did, kept
        return did, ""

    with ThreadPoolExecutor(6) as pool:
        got = list(pool.map(one, rows))
    with db.session() as c:
        logos = set(json.loads((c.execute("SELECT v FROM kv WHERE k = 'feed_logos'").fetchone() or ["[]"])[0]))
        c.executemany("UPDATE docs SET thumb = ? WHERE id = ? AND (thumb IS NULL OR thumb LIKE 'http%')",
                      [("" if t in logos else t, did) for did, t in got])
        # A picture three posts of one feed share is the feed's own (its logo, a newsletter's header), not
        # theirs: it goes from them, and from the posts that bring it later.
        same = {r[0] for r in c.execute("SELECT thumb FROM docs WHERE where_ = 'feed' AND thumb LIKE '/api/thumb/%' "
                                        "GROUP BY feed, thumb HAVING COUNT(*) >= 3")}
        if same:
            c.executemany("UPDATE docs SET thumb = '' WHERE where_ = 'feed' AND thumb = ?", [(t,) for t in same])
            c.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_logos', ?)", (json.dumps(sorted(logos | same)),))
        _drop_pictures(c, {t for _, t in got if t in logos} | same)
    return sum(1 for _, t in got if t and t not in logos | same)


def _drop_pictures(conn, names):
    """The kept pictures no doc shows any more (nor a book added from Hardcover, whose cover is kept the
    same way): their files go, so the Feed's pictures don't pile up as its posts come and go."""
    from .. import pages
    for t in set(names):
        if (t or "").startswith("/api/thumb/") and not conn.execute("SELECT 1 FROM docs WHERE thumb = ?", (t,)).fetchone() \
                and not conn.execute("SELECT 1 FROM book_adds WHERE cover = ?", (t,)).fetchone():
            (pages.THUMBS / t.rsplit("/", 1)[1]).unlink(missing_ok=True)


def _forget(conn, settings):
    """As freshrss.sync does: old seen posts that were never highlighted, sent to the Kindle or starred in
    a reader app (greader.py) go, once they're older than the window; what each feed gave stays in
    feed_seen (a year), so they don't come back."""
    expire = int(settings.get("feed_expire_days", 30))
    keep = ("id NOT IN (SELECT DISTINCT book_id FROM highlights WHERE book_id IS NOT NULL) AND id NOT IN (SELECT doc_id FROM kindle_sent) "
            "AND COALESCE(starred, 0) = 0")
    forget = int(time.time()) - max(30, expire + 2) * 86400
    pictures = [r[0] for r in conn.execute("SELECT thumb FROM docs WHERE where_ = 'feed' AND status IN ('seen', 'deleted') AND added < ? "
                                           f"AND {keep} AND thumb LIKE '/api/thumb/%'", (forget,))]
    conn.execute("DELETE FROM doc_content WHERE id IN (SELECT id FROM docs WHERE where_ = 'feed' AND status IN ('seen', 'deleted') AND added < ? "
                 f"AND {keep})", (forget,))
    conn.execute(f"DELETE FROM docs WHERE where_ = 'feed' AND status IN ('seen', 'deleted') AND added < ? AND {keep}", (forget,))
    _drop_pictures(conn, pictures)
    # the pool's posts the Edition didn't take: gone after POOL_DAYS (feed_seen still keeps them from coming back)
    old = int(time.time()) - POOL_DAYS * 86400
    conn.execute(f"DELETE FROM doc_content WHERE id IN (SELECT id FROM docs WHERE where_ = 'pool' AND added < ? AND {keep})", (old,))
    conn.execute(f"DELETE FROM docs WHERE where_ = 'pool' AND added < ? AND {keep}", (old,))
    conn.execute("DELETE FROM feed_seen WHERE at < ?", (int(time.time()) - 400 * 86400,))


# ---------------------------------------------------------------- the move from FreshRSS

def _freshrss_attrs():
    """FreshRSS's own settings for each feed (its API doesn't give them): {url: attributes}. Read from
    its database through the container's PHP, read-only; {} when that isn't possible."""
    import subprocess
    php = ('$db=new PDO("sqlite:/var/www/FreshRSS/data/users/Franz_Rosenzweig/db.sqlite",null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);'
           'echo json_encode($db->query("select url, attributes from feed")->fetchAll(PDO::FETCH_KEY_PAIR));')
    try:
        out = subprocess.run(["docker", "exec", "freshrss", "php", "-r", php], capture_output=True, text=True, timeout=60).stdout
        return {u: json.loads(a) if a else {} for u, a in json.loads(out or "{}").items()}
    except Exception:  # noqa: BLE001
        return {}


def import_freshrss(conn, settings):
    """FreshRSS's feeds, folders, names, icons and the settings Daf honours, into feeds; everything it
    has already brought counted as seen; then Daf is in charge of the Feed. Returns what it did."""
    from . import freshrss
    subs = freshrss.subscriptions()
    attrs = _freshrss_attrs()
    now, icons, kept = int(time.time()), 0, {}
    for s in subs:
        if s["url"] in kept:               # FreshRSS followed it twice: one feed, its posts with it
            conn.execute("UPDATE docs SET feed = ? WHERE feed = ?", (kept[s["url"]], s["id"]))
            continue
        kept[s["url"]] = s["id"]
        a = attrs.get(s["url"]) or {}
        keep = {k: a[k] for k in ("read_upon_reception", "ssl_verify", "timeout") if a.get(k) is not None}
        key = None
        if s["icon"]:
            try:
                with urllib.request.urlopen(config.FRESHRSS_URL + "/f.php?" + urllib.parse.urlencode({"h": s["icon"]}), timeout=10) as r:
                    data, ctype = r.read(300_000), r.headers.get("Content-Type", "image/x-icon")
                ext = {"image/png": "png", "image/svg+xml": "svg", "image/gif": "gif", "image/jpeg": "jpg", "image/webp": "webp"}.get(ctype.split(";")[0], "ico")
                ICONS.mkdir(parents=True, exist_ok=True)
                (ICONS / f"{s['icon']}.{ext}").write_bytes(data)
                key, icons = s["icon"], icons + 1
            except Exception:  # noqa: BLE001
                key = None
        conn.execute("INSERT OR REPLACE INTO feeds (id, url, title, site, folder, icon, attrs, added) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (s["id"], s["url"], s["title"], s["site"], s["folder"], key, json.dumps(keep) if keep else None, now))
    # every post FreshRSS has brought in the window, read or not, by its link: seen
    expire = int(settings.get("feed_expire_days", 30))
    since = now - (max(30, expire) + 30) * 86400
    seen, c = 0, None
    while True:
        q = {"n": 1000, "output": "json", "ot": since}
        if c:
            q["c"] = c
        d = freshrss._get("/reader/api/0/stream/contents/user/-/state/com.google/reading-list?" + urllib.parse.urlencode(q))  # noqa: SLF001
        rows = []
        for it in d.get("items", []):
            link = (it.get("canonical") or it.get("alternate") or [{}])[0].get("href", "")
            feed = (it.get("origin") or {}).get("streamId")
            if link and feed:
                rows.append((kept.get(next((x["url"] for x in subs if x["id"] == feed), ""), feed), "link:" + link, now))
        conn.executemany("INSERT OR IGNORE INTO feed_seen (feed, key, at) VALUES (?, ?, ?)", rows)
        seen += len(rows)
        c = d.get("continuation")
        if not d.get("items") or not c:
            break
    # and what Daf already holds from them
    conn.execute("INSERT OR IGNORE INTO feed_seen (feed, key, at) SELECT feed, 'link:' || url, ? FROM docs "
                 "WHERE where_ = 'feed' AND feed IS NOT NULL AND url IS NOT NULL AND url != ''", (now,))
    conn.execute("UPDATE feeds SET fetched = ?", (now,))           # FreshRSS read them just now
    s = config.load_settings()
    s["feed_reader"] = "daf"
    config.save_settings(s)
    return {"feeds": len(kept), "folders": len({x["folder"] for x in subs if x["folder"]}), "icons": icons, "seen": seen,
            "settings": sum(1 for x in subs if (attrs.get(x["url"]) or {}).get("read_upon_reception"))}
