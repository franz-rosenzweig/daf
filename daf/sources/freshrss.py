"""The Feed: FreshRSS through its Google Reader API (http://127.0.0.1:8080).

Daf keeps the newest unread items (back to the expiry window) as `docs` with
where='feed', and their cleaned text in `doc_content`. Read state is shared both
ways: marking seen in Daf marks read in FreshRSS (so Read You agrees), and an item
read elsewhere drops out of Daf's Unseen on the next sync.
"""
import json
import time
import urllib.parse
import urllib.request

from .. import config, content, secrets

BASE = config.FRESHRSS_URL + "/api/greader.php"
READ = "user/-/state/com.google/read"
STAR = "user/-/state/com.google/starred"
_auth = {"token": None, "at": 0, "edit": None}


class FreshRSSError(Exception):
    pass


def _login():
    user, pw = secrets.freshrss()
    if not pw:
        raise FreshRSSError("no FreshRSS API password (HOMEPAGE_VAR_FRESHRSS_PASS)")
    data = urllib.parse.urlencode({"Email": user, "Passwd": pw}).encode()
    try:
        r = urllib.request.urlopen(BASE + "/accounts/ClientLogin", data, timeout=15).read().decode()
    except urllib.error.HTTPError as e:
        raise FreshRSSError(f"FreshRSS refused the login ({e.code})") from e
    tok = next((l[5:] for l in r.splitlines() if l.startswith("Auth=")), None)
    if not tok:
        raise FreshRSSError("FreshRSS gave no token")
    _auth.update(token=tok, at=time.time(), edit=None)


def _req(path, data=None, retry=True):
    if not _auth["token"] or time.time() - _auth["at"] > 3600:
        _login()
    req = urllib.request.Request(BASE + path, data=data, headers={"Authorization": "GoogleLogin auth=" + _auth["token"]})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry:
            _auth["token"] = None
            return _req(path, data, retry=False)
        raise FreshRSSError(f"FreshRSS {e.code} on {path.split('?')[0]}") from e


def _get(path):
    return json.loads(_req(path))


def _edit_token():
    if not _auth["edit"]:
        _auth["edit"] = _req("/reader/api/0/token").decode().strip()
    return _auth["edit"]


def short_id(long_id):
    return long_id.rsplit("/", 1)[-1]


def edit(item_ids, add=None, remove=None):
    if not item_ids:
        return
    for i in range(0, len(item_ids), 200):
        fields = [("i", "tag:google.com,2005:reader/item/" + x) for x in item_ids[i:i + 200]]
        if add:
            fields.append(("a", add))
        if remove:
            fields.append(("r", remove))
        fields.append(("T", _edit_token()))
        _req("/reader/api/0/edit-tag", urllib.parse.urlencode(fields).encode())


def mark_read(item_ids, read=True):
    edit(item_ids, add=READ if read else None, remove=None if read else READ)


def star(item_ids, on=True):
    edit(item_ids, add=STAR if on else None, remove=None if on else STAR)


def subscribe(url, folder=None):
    """Follow a site or a feed in FreshRSS (it finds the feed on a site's page). Returns its title."""
    fields = [("quickadd", url), ("T", _edit_token())]
    d = json.loads(_req("/reader/api/0/subscription/quickadd", urllib.parse.urlencode(fields).encode()) or b"{}")
    if not d.get("streamId"):
        raise ValueError("FreshRSS found no feed there")
    if folder:
        _req("/reader/api/0/subscription/edit", urllib.parse.urlencode(
            [("ac", "edit"), ("s", d["streamId"]), ("a", "user/-/label/" + folder), ("T", _edit_token())]).encode())
    return d.get("streamName") or url


def subscriptions():
    """The feeds FreshRSS follows: [{id ("feed/12"), title, folder, url, site, icon (f.php's hash)}]."""
    d = _get("/reader/api/0/subscription/list?output=json")
    out = []
    for s in d.get("subscriptions", []):
        cats = [c.get("label") or c.get("id", "").split("/label/")[-1] for c in s.get("categories", []) or []]
        icon = urllib.parse.parse_qs(urllib.parse.urlparse(s.get("iconUrl") or "").query).get("h", [""])[0]
        out.append({"id": s["id"], "title": (s.get("title") or s.get("url") or s["id"]).strip(), "folder": cats[0] if cats else "",
                    "url": s.get("url", ""), "site": s.get("htmlUrl", ""), "icon": icon})
    return out


def edit_subscription(stream, title=None, folder=None, old_folder=None):
    """Rename a feed, or move it to another folder ("" for none)."""
    fields = [("ac", "edit"), ("s", stream)]
    if title:
        fields.append(("t", title))
    if folder is not None and folder != old_folder:
        if folder:
            fields.append(("a", "user/-/label/" + folder))
        if old_folder:
            fields.append(("r", "user/-/label/" + old_folder))
    fields.append(("T", _edit_token()))
    _req("/reader/api/0/subscription/edit", urllib.parse.urlencode(fields).encode())


def unsubscribe(stream):
    _req("/reader/api/0/subscription/edit", urllib.parse.urlencode([("ac", "unsubscribe"), ("s", stream), ("T", _edit_token())]).encode())


def icon(h):
    """A feed's icon from FreshRSS (f.php), as (bytes, type)."""
    with urllib.request.urlopen(config.FRESHRSS_URL + "/f.php?" + urllib.parse.urlencode({"h": h}), timeout=10) as r:
        return r.read(), r.headers.get("Content-Type", "image/png")


def folders():
    d = _get("/reader/api/0/tag/list?output=json")
    return sorted(t["id"].split("/label/", 1)[1] for t in d.get("tags", []) if "/label/" in t.get("id", ""))


def mark_all_read_before(ts):
    """Everything in the reading list older than ts (epoch seconds) becomes read."""
    fields = [("s", "user/-/state/com.google/reading-list"), ("ts", str(int(ts) * 1000000)), ("T", _edit_token())]
    _req("/reader/api/0/mark-all-as-read", urllib.parse.urlencode(fields).encode())


def unread_ids():
    out, c = [], None
    while True:
        q = {"s": "user/-/state/com.google/reading-list", "xt": READ, "n": 10000, "output": "json"}
        if c:
            q["c"] = c
        d = _get("/reader/api/0/stream/items/ids?" + urllib.parse.urlencode(q))
        out += [short_id(x["id"]) if "/" in str(x["id"]) else format(int(x["id"]), "016x") for x in d.get("itemRefs", [])]
        c = d.get("continuation")
        if not c:
            return set(out)


def unread_counts():
    d = _get("/reader/api/0/unread-count?output=json")
    labels = {u["id"].split("/label/")[-1]: u["count"] for u in d.get("unreadcounts", []) if "/label/" in u["id"]}
    return d.get("max", 0), labels


def _kind(item):
    for e in item.get("enclosure", []) or []:
        if str(e.get("type", "")).startswith("audio/"):
            return "podcast", e.get("href")
    url = (item.get("canonical") or item.get("alternate") or [{}])[0].get("href", "")
    if "youtube.com/watch" in url or "youtu.be/" in url:
        return "video", None
    return "article", None


def sync(conn, settings, max_items=1500):
    """Fetch unread items newer than the expiry window. Returns (new, total unread)."""
    expire = int(settings.get("feed_expire_days", 30))
    horizon = int(time.time()) - (expire + 2) * 86400
    known = {r[0] for r in conn.execute("SELECT id FROM docs WHERE where_ = 'feed'")}
    newest = conn.execute("SELECT MAX(published) FROM docs WHERE where_ = 'feed'").fetchone()[0] or 0
    since = max(horizon, newest - 6 * 3600) if newest else horizon
    # A longer window than last time (Preferences → The Feed lets go after): once, back to its start,
    # for the unread items Daf never pulled because they were older than the old window.
    was = conn.execute("SELECT v FROM kv WHERE k = 'feed_window'").fetchone()
    grew = not was or int(was[0]) < expire
    if grew:
        since, max_items = horizon, max(max_items, 8000)
    fetched, c, new = 0, None, 0
    while fetched < max_items:
        q = {"xt": READ, "n": 200, "output": "json", "ot": since}
        if c:
            q["c"] = c
        d = _get("/reader/api/0/stream/contents/user/-/state/com.google/reading-list?" + urllib.parse.urlencode(q))
        items = d.get("items", [])
        for it in items:
            sid = short_id(it["id"])
            did = "fr:" + sid
            fetched += 1
            if did in known:
                continue
            raw = (it.get("content") or it.get("summary") or {}).get("content", "")
            bl = content.blocks(raw)
            kind, enclosure = _kind(it)
            cats = [x.split("/label/")[-1] for x in it.get("categories", []) if "/label/" in x]
            url = (it.get("canonical") or it.get("alternate") or [{}])[0].get("href", "")
            conn.execute(
                "INSERT OR IGNORE INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, "
                "words, summary, enclosure, ext_id, feed) VALUES (?, ?, 'feed', 'unseen', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (did, kind, (it.get("title") or "Untitled").strip(), "" if "@" in (it.get("author") or "") else (it.get("author") or "").strip()[:120],
                 (it.get("origin") or {}).get("title", ""), cats[0] if cats else "", url, it.get("published"),
                 int(it.get("crawlTimeMsec") or 0) // 1000 or int(time.time()), content.words(bl), content.summary(bl),
                 enclosure, sid, (it.get("origin") or {}).get("streamId")))
            conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)",
                         (did, json.dumps(bl), int(time.time())))
            new += 1
        c = d.get("continuation")
        if not items or not c:
            break
    # Read elsewhere (Read You, the desk): out of Unseen here too.
    unread = unread_ids()
    conn.execute(f"UPDATE docs SET status = 'seen' WHERE where_ = 'feed' AND status = 'unseen' AND ext_id NOT IN "
                 f"({','.join('?' * len(unread))})" if unread else "UPDATE docs SET status = 'seen' WHERE where_ = 'feed' AND status = 'unseen'",
                 tuple(unread))
    total, labels = unread_counts()
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_counts', ?)", (json.dumps({"total": total, "labels": labels}),))
    if grew or (was and int(was[0]) != expire):
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_window', ?)", (str(expire),))
    # Forget old seen items that were never highlighted or sent to the Kindle (highlights may still come from there),
    # once they're older than the window too.
    keep = "id NOT IN (SELECT DISTINCT book_id FROM highlights WHERE book_id IS NOT NULL) AND id NOT IN (SELECT doc_id FROM kindle_sent)"
    forget = int(time.time()) - max(30, expire + 2) * 86400
    conn.execute("DELETE FROM doc_content WHERE id IN (SELECT id FROM docs WHERE where_ = 'feed' AND status IN ('seen', 'deleted') AND added < ? "
                 f"AND {keep})", (forget,))
    conn.execute(f"DELETE FROM docs WHERE where_ = 'feed' AND status IN ('seen', 'deleted') AND added < ? AND {keep}", (forget,))
    return new, total
