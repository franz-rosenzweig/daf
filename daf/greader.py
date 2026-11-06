"""Daf's Feed in other reader apps: the Google Reader API, as FreshRSS speaks it, at /api/greader.php.

Read You, NetNewsWire, Reeder, FocusReader, Fluent Reader, newsboat and the rest were written and
tested against FreshRSS's p/api/greader.php, so this follows it: the same paths (an app's "FreshRSS"
account adds /api/greader.php to the server's address itself; a "Google Reader API" account is
given the whole of it), the same answers, the same quirks.

What an app sees is Daf's Feed: the items with where='feed' that aren't deleted, from the feeds Daf
follows, each folder a label (user/-/label/<folder>). An item is read when Daf has it seen, or when
it's older than the Feed's window (Preferences → The Feed lets go after), the way Daf's own Unseen
counts. A star is Daf's Shortlist: starring an item saves it to the Library and puts it on the
Shortlist (reader.save_to_library, reader.set_starred) and sets docs.starred on the Feed item, which
the app reads back; a Library item starred or unstarred in Daf takes its Feed item along
(reader.set_starred). A starred Feed item is never forgotten (rss._forget). Following, renaming,
moving and unfollowing go through feedsrc and reader.edit_feed / unfollow_feed, as the Sources
sheet's do.

Item ids: apps want a 64-bit number that grows with time (FreshRSS's is the microsecond it fetched
the item, and some apps can't take one past 2^63). The items FreshRSS brought (fr:<16 hex>) keep
FreshRSS's own; Daf's own (rss:<sha>) get the microsecond of their docs.added, one up when that's
taken. The table greader_ids keeps them, filled in as the API is asked (_assign). The long form is
tag:google.com,2005:reader/item/<16 hex>, the short one its decimal.

Sign-in: Daf's username and an API password of its own, made in Preferences → Reader apps and
shown once, never Daf's own password. STATE/greader.json (mode 600) keeps it scrypt-hashed, with the
secret the tokens are signed with; a new password brings a new secret, removing it takes the secret
away, and every token stops working either way. ClientLogin answers SID/LSID/Auth as FreshRSS does,
Auth being "<user>/<HMAC>"; every other call needs "Authorization: GoogleLogin auth=<it>". The T
token (reader/api/0/token) is another HMAC, checked where FreshRSS checks it (edit-tag, rename-tag,
disable-tag, mark-all-as-read), with FreshRSS's allowance for "" and "x" (FeedMe and Reeder send
those; the Authorization header is what guards, and no browser sends it for another site). Five
wrong passwords from one address in 15 minutes lock it out for 15; twenty from anywhere in an hour
pause API sign-ins for 15 and say so (app._alert). Every answer is "Cache-Control: private,
no-cache", so Cloudflare keeps none of it.

Feed icons and the posts' pictures go out at /api/greader.php/icon|pic/<signature>/<name>, signed
with the same secret, since an app fetches them without the token.
"""
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.parse

from fastapi import APIRouter, Depends, Request, Response
from starlette.concurrency import run_in_threadpool

from . import auth, config, db, reader
from .sources import feedsrc

log = logging.getLogger("daf.greader")

PATH = config.STATE / "greader.json"
LONG = "tag:google.com,2005:reader/item/"
READING = "user/-/state/com.google/reading-list"
READ = "user/-/state/com.google/read"
UNREAD = "user/-/state/com.google/unread"
STARRED = "user/-/state/com.google/starred"
LABEL = "user/-/label/"
HEADERS = {"Cache-Control": "private, no-cache", "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; sandbox",
           "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Authorization",
           "Access-Control-Allow-Methods": "GET, POST", "Access-Control-Max-Age": "600"}
MAX_BODY = 1 << 20              # as FreshRSS reads it
MAX_IDS = 100_000               # stream/items/ids
MAX_ITEMS = 1000                # stream/contents and items/contents, per answer
UNREAD_SQL = "(d.status = 'unseen' AND d.added >= ?)"
FIELDS = ("g.gid, d.id, d.title, d.author, d.url, d.published, d.added, d.status, d.starred, d.feed, d.category, d.source, "
          "d.kind, d.enclosure, d.thumb, d.summary, d.ext_id")


# ---------------------------------------------------------------- the API password

_lock = threading.Lock()
_used = {"at": 0, "saved": 0.0}
LETTERS = "abcdefghjkmnpqrstuvwxyz23456789"      # nothing to mistake for something else when typed


def _load():
    try:
        a = json.loads(PATH.read_text())
    except (OSError, ValueError):
        return None
    return a if isinstance(a, dict) and a.get("hash") and a.get("salt") and a.get("secret") else None


def _save(a):
    config.STATE.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(a))
    os.chmod(tmp, 0o600)
    tmp.replace(PATH)


def make_password():
    """A new API password (four groups of five), replacing the old one and every token made with it.
    Returns it: this is the only time it's known."""
    pw = "-".join("".join(secrets.choice(LETTERS) for _ in range(5)) for _ in range(4))
    salt = secrets.token_bytes(16)
    with _lock:
        _save({"salt": salt.hex(), "hash": auth._scrypt(pw, salt).hex(), "secret": secrets.token_hex(32), "made": int(time.time())})
        _used.update(at=0, saved=0.0)
    return pw


def remove_password():
    with _lock:
        PATH.unlink(missing_ok=True)
        _used.update(at=0, saved=0.0)


def status():
    a = _load()
    if not a:
        return {"has_password": False, "made": None, "used": None}
    return {"has_password": True, "made": a.get("made"), "used": max(a.get("used") or 0, _used["at"]) or None}


def check_login(name, password):
    """Daf's username and the API password. The password is checked either way, so a wrong name takes as long."""
    a = _load()
    got = auth._scrypt(str(password or "")[:256], bytes.fromhex(a["salt"]) if a else b"\0" * 16).hex()
    ok_pw = bool(a) and hmac.compare_digest(got, a["hash"])
    ok_user = hmac.compare_digest(str(name or "").strip().lower().encode(), auth.username().encode())
    return ok_pw and ok_user


def _key():
    a = _load()
    return (bytes.fromhex(a["secret"]), auth.username()) if a else (None, None)


def _mac(key, what):
    return hmac.new(key, what.encode(), hashlib.sha256).hexdigest()


def auth_token():
    key, name = _key()
    return f"{name}/{_mac(key, 'auth|' + name)}"


def edit_token():
    key, name = _key()
    return _mac(key, "edit|" + name)[:57]           # Google's were 57 characters, and some apps count


def token_ok(tok):
    key, name = _key()
    if not key or not tok or "/" not in tok:
        return False
    who, mac = tok.rsplit("/", 1)
    return hmac.compare_digest(who.encode(), name.encode()) & hmac.compare_digest(mac.encode(), _mac(key, "auth|" + name).encode())


def _touch():
    """When an app last used it, for Preferences: kept in memory, written down every ten minutes at most."""
    now = time.time()
    _used["at"] = int(now)
    if now - _used["saved"] > 600:
        with _lock:
            a = _load()
            if a:
                a["used"] = int(now)
                _save(a)
            _used["saved"] = now


# Wrong passwords: five from one address in 15 minutes lock it out for 15; twenty from anywhere in an
# hour pause every API sign-in for 15 minutes, and Daf says so. Apart from the web sign-in's, so an
# app with an old password can't lock the browser out.
_fails = {}
_pause = {"until": 0.0}
_flock = threading.Lock()


def _throttled(ip):
    now = time.time()
    with _flock:
        return now < _pause["until"] or sum(1 for t in _fails.get(ip, []) if now - t < 900) >= 5


def _failed(ip):
    now = time.time()
    with _flock:
        for k in [k for k, ts in _fails.items() if not any(now - t < 3600 for t in ts)]:
            del _fails[k]
        _fails.setdefault(ip, []).append(now)
        locked = sum(1 for t in _fails[ip] if now - t < 900) == 5
        everyone = sum(1 for ts in _fails.values() for t in ts if now - t < 3600)
        pause = everyone >= 20 and now >= _pause["until"]
        if pause:
            _pause["until"] = now + 900
    if locked:
        log.warning("reader-app sign-in locked for %s", ip)
    if pause:
        log.warning("reader-app sign-ins paused")
        from .app import _alert
        _alert(f"{everyone} wrong API passwords for Daf's reader apps in the last hour. Their sign-in is paused for 15 minutes.")


def _succeeded(ip):
    with _flock:
        _fails.pop(ip, None)


# ---------------------------------------------------------------- answers

class _Stop(Exception):
    def __init__(self, response):
        self.response = response


def _text(s, status=200, extra=None):
    return Response((s or "").encode("utf-8", "replace"), status_code=status, headers={**HEADERS, **(extra or {})},
                    media_type="text/plain; charset=UTF-8")


def _json(obj):
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "replace")
    return Response(body, headers=HEADERS, media_type="application/json; charset=UTF-8")


def _bad():
    raise _Stop(_text("Bad Request!", 400))


def _unauthorized():
    raise _Stop(_text("Unauthorized!", 401, {"Google-Bad-Token": "true"}))


class _Params:
    """A request's fields: the form body first, then the query (FreshRSS reads some from either)."""

    def __init__(self, request, body):
        self.query = list(request.query_params.multi_items())
        try:
            self.body = urllib.parse.parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True) if body else []
        except ValueError:
            self.body = []

    def get(self, k, default=""):
        for src in (self.body, self.query):
            for kk, v in src:
                if kk == k:
                    return v
        return default

    def all(self, k):
        return [v for kk, v in self.body if kk == k] or [v for kk, v in self.query if kk == k]


def _base(request):
    """This server's address as the app reached it (through the tunnel it's https)."""
    from .app import is_https
    host = request.headers.get("host") or ""
    if not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]{1,255}", host):
        return config.public_url()
    return ("https" if is_https(request) else request.url.scheme) + "://" + host


def long_id(gid):
    return LONG + format(gid, "016x")


def parse_id(s):
    """An item id as an app sends it: the decimal short form, or the long form's (or bare) hex, as
    FreshRSS reads them (digits starting with 0 are hex)."""
    s = str(s or "").strip()
    if s.isdigit() and not s.startswith("0"):
        n = int(s)
    else:
        h = s.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[0-9a-fA-F]{1,16}", h):
            return None
        n = int(h, 16)
    return n if 0 < n < 1 << 63 else None


def _norm(s):
    """user/<anyone>/… is user/-/…, as Google had it."""
    s = str(s or "").strip()
    m = re.match(r"^user/[^/]+/(state|label)/(.*)$", s, re.S)
    return f"user/-/{m.group(1)}/{m.group(2)}" if m else s


def _plain(t, extended=False):
    """FreshRSS's escapeToUnicodeAlternative: & < > (and more for a feed's name) as their wide forms,
    for the apps that show a title as HTML."""
    t = html.unescape(t or "")
    swap = {"&": "＆", "<": "＜", ">": "＞"}
    if extended:
        swap.update({"'": "’", '"': "＂", "^": "＾", "?": "？", "\\": "＼", "/": "／", ",": "，", ";": "；"})
    return "".join(swap.get(ch, ch) for ch in t).strip()


# ---------------------------------------------------------------- what an app sees

def _assign(c):
    """A GReader id for every Feed item that hasn't one (see the top of this file), and none kept for
    items Daf has forgotten. Committed at once, so the write lock isn't held while an answer is made."""
    rows = c.execute("SELECT d.id, d.added FROM docs d LEFT JOIN greader_ids g ON g.doc = d.id WHERE d.where_ = 'feed' "
                     "AND g.doc IS NULL ORDER BY (d.id NOT LIKE 'fr:%'), d.added, d.rowid").fetchall()
    if not rows:
        return
    for did, added in rows:
        m = re.fullmatch(r"fr:([0-9a-f]{16})", did)
        gid = int(m.group(1), 16) if m else 0
        if not 0 < gid < 1 << 62 or c.execute("SELECT 1 FROM greader_ids WHERE gid = ?", (gid,)).fetchone():
            base = int(added or time.time()) * 1_000_000
            top = c.execute("SELECT MAX(gid) FROM greader_ids WHERE gid >= ? AND gid < ?", (base, base + 1_000_000)).fetchone()[0]
            gid = base if top is None else top + 1
        while not c.execute("INSERT OR IGNORE INTO greader_ids (gid, doc) VALUES (?, ?)", (gid, did)).rowcount:
            if c.execute("SELECT 1 FROM greader_ids WHERE doc = ?", (did,)).fetchone():
                break                       # another request gave it one a moment ago
            gid += 1
    c.execute("DELETE FROM greader_ids WHERE doc NOT IN (SELECT id FROM docs)")
    c.commit()


def _visible(by_id=False):
    """The Feed's items an app may see: not deleted, and (when Daf reads the feeds) from a feed it still
    follows, or starred. Asked for by id, any item that isn't deleted."""
    q = "d.where_ = 'feed' AND d.status != 'deleted'"
    if not by_id and feedsrc.daf():
        q += " AND (d.feed IN (SELECT id FROM feeds) OR COALESCE(d.starred, 0) = 1)"
    return q


def _subs(c):
    try:
        return feedsrc.get().subscriptions(conn=c)
    except Exception:  # noqa: BLE001 - FreshRSS not answering: the list Daf kept
        return json.loads((c.execute("SELECT v FROM kv WHERE k = 'feed_subs'").fetchone() or ["[]"])[0])


def _feed_id(c, s):
    """feed/12, or feed/<its address> as Google named them, to Daf's feed id."""
    rest = re.sub(r"^(feed/)+", "", str(s or ""))
    if rest.isdigit():
        return "feed/" + rest
    r = c.execute("SELECT id FROM feeds WHERE url = ?", (rest,)).fetchone()
    if r:
        return r[0]
    return next((x["id"] for x in _subs(c) if x.get("url") == rest), None)


def _scope(c, s, exp):
    """A stream as SQL over docs d: (expression, args), "0" for one Daf doesn't have."""
    s = _norm(s)
    if s in ("", READING, "user/-/state/org.freshrss/main"):
        return "1", []
    if s == STARRED:
        return "COALESCE(d.starred, 0) = 1", []
    if s == UNREAD:
        return UNREAD_SQL, [exp]
    if s == READ:
        return "NOT " + UNREAD_SQL, [exp]
    if s.startswith("feed/"):
        fid = _feed_id(c, s)
        return ("d.feed = ?", [fid]) if fid else ("0", [])
    if s.startswith(LABEL) and len(s) > len(LABEL):
        return "d.category = ?", [s[len(LABEL):]]
    return "0", []


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _filters(c, stream, P, exp):
    """A stream with the request's it, xt, ot, nt, r and c: (where clauses, args, ascending)."""
    where, args = [_visible()], []
    e, a = _scope(c, stream, exp)
    where.append(e)
    args += a
    it = P.get("it")
    if it:
        e, a = _scope(c, it, exp)
        where.append(e)
        args += a
    for xt in P.all("xt"):
        if xt:
            e, a = _scope(c, xt, exp)
            where.append(f"NOT ({e})")
            args += a
    ot, nt = _int(P.get("ot")), _int(P.get("nt"))
    if ot > 0:
        where.append("g.gid >= ?")
        args.append(ot * 1_000_000)
    if nt > 0:
        where.append("g.gid < ?")
        args.append((nt + 1) * 1_000_000)
    asc = P.get("r") == "o"
    cont = P.get("c").strip()
    if cont.isdigit():                     # where the last answer ended (its last item's id)
        where.append("g.gid > ?" if asc else "g.gid < ?")
        args.append(int(cont))
    return where, args, asc


def _count(P, cap):
    n = _int(P.get("n"), 20)
    return max(1, min(n if n > 0 else 20, cap))


def _signed(base, kind, name):
    key, _ = _key()
    return f"{base}/api/greader.php/{kind}/{_mac(key, kind + '|' + name)[:32]}/{name}" if key else ""


def _attr(s):
    return html.escape(str(s or ""), quote=True)


TAGS = {"h1": "h2", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h4", "h6": "h4", "pre": "pre", "li": "li"}


def _html(blocks, summary, picture=None, audio=None):
    """An item's text as HTML, from Daf's blocks (the whole article once Daf has it), with the post's
    picture at the top when the text has none, and an episode's audio at the end, as FreshRSS adds them."""
    from .kindlesend import _inline          # a block's inline HTML, cleaned to safe, closed tags
    out, in_list, has_img = [], False, False
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        t = b.get("t")
        if t == "img":
            src = str(b.get("src") or "")
            if src.startswith(("http://", "https://")):
                if in_list:
                    out.append("</ul>")
                    in_list = False
                out.append(f'<figure><img src="{_attr(src)}" alt="{_attr(b.get("alt"))}"></figure>')
                has_img = True
            continue
        inner = _inline(b)
        if not inner.strip():
            continue
        if t == "li" and not in_list:
            out.append("<ul>")
            in_list = True
        elif t != "li" and in_list:
            out.append("</ul>")
            in_list = False
        if t == "blockquote":
            out.append(f"<blockquote><p>{inner}</p></blockquote>")
        else:
            tag = TAGS.get(t, "p")
            out.append(f"<{tag}>{inner}</{tag}>")
    if in_list:
        out.append("</ul>")
    if not out and summary:
        out.append(f"<p>{html.escape(summary, quote=False)}</p>")
    if picture and not has_img:
        out.insert(0, f'<figure><img src="{_attr(picture)}" alt=""></figure>')
    if audio:
        out.append(f'<p><audio controls preload="none" src="{_attr(audio)}"></audio></p>')
    return "".join(out)


AUDIO = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "mp4": "audio/mp4", "aac": "audio/aac", "ogg": "audio/ogg", "oga": "audio/ogg",
         "opus": "audio/ogg", "wav": "audio/wav", "flac": "audio/flac"}


def _items(c, request, rows, exp):
    """Rows (FIELDS) as FreshRSS's items ('compat' mode: the text in summary.content)."""
    feeds = {x["id"]: x for x in _subs(c)}
    texts = {}
    ids = [r["id"] for r in rows]
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for did, bl in c.execute(f"SELECT id, blocks FROM doc_content WHERE id IN ({','.join('?' * len(part))})", part):
            try:
                texts[did] = json.loads(bl)
            except ValueError:
                pass
    base = _base(request)
    out = []
    for r in rows:
        gid, url = r["gid"], r["url"] or ""
        f = feeds.get(r["feed"]) or {}
        read = not (r["status"] == "unseen" and (r["added"] or 0) >= exp)
        cats = [READING] + ([LABEL + r["category"]] if r["category"] else []) + ([READ] if read else []) + ([STARRED] if r["starred"] else [])
        thumb = r["thumb"] or ""
        m = re.fullmatch(r"/api/thumb/([0-9a-f]{16})\.jpg", thumb)
        picture = _signed(base, "pic", m.group(1)) if m else ""
        audio = r["enclosure"] if r["kind"] == "podcast" and str(r["enclosure"] or "").startswith(("http://", "https://")) else ""
        content = _html(texts.get(r["id"]), r["summary"], picture, audio)
        if len(content.encode()) > 500_000:          # as FreshRSS cuts it
            content = content.encode()[:500_000].decode("utf-8", "ignore")
        when = int(r["published"] or r["added"] or 0)
        it = {"id": long_id(gid), "crawlTimeMsec": str(gid // 1000), "timestampUsec": str(gid), "published": when, "updated": when,
              "title": _plain(r["title"] or "Untitled"), "canonical": [{"href": url}], "alternate": [{"href": url}], "categories": cats,
              "origin": {"streamId": r["feed"] or "", "htmlUrl": f.get("site") or "", "title": f.get("title") or r["source"] or ""},
              "summary": {"content": content}}
        if r["author"]:
            it["author"] = r["author"]
        enc = []
        if audio:
            ext = urllib.parse.urlsplit(audio).path.rsplit(".", 1)[-1].lower()
            enc.append({"href": audio, "type": AUDIO.get(ext, "audio/mpeg")})
        if picture:
            enc.append({"href": picture, "type": "image/jpeg"})
        if enc:
            it["enclosure"] = enc
        out.append(it)
    return out


def _rows(c, ids, by_id=True):
    """The Feed items with these GReader ids."""
    out = []
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        out += c.execute(f"SELECT {FIELDS} FROM greader_ids g JOIN docs d ON d.id = g.doc WHERE {_visible(by_id)} "
                         f"AND g.gid IN ({','.join('?' * len(part))})", part).fetchall()
    return out


# ---------------------------------------------------------------- what an app does

def _read(c, rows, read):
    """Seen or unseen, as Daf's own Mark seen does (FreshRSS told too, while it was in charge)."""
    change = [r for r in rows if (r["status"] != "unseen") != read]
    if not change:
        return
    feedsrc.get().mark_read([r["ext_id"] for r in change if r["ext_id"]], read=read)
    c.executemany("UPDATE docs SET status = ? WHERE id = ? AND status != 'deleted'", [("seen" if read else "unseen", r["id"]) for r in change])


def _library_copies(c, url):
    from . import pages
    key = pages.norm_url(url)
    return [r["id"] for r in c.execute("SELECT id, url FROM docs WHERE where_ = 'library' AND url IS NOT NULL AND instr(lower(url), ?) > 0",
                                       (key.split("://", 1)[-1].lower(),)).fetchall() if pages.norm_url(r["url"]) == key]


def _star(c, rows, on):
    """A star from an app is the Shortlist: the item goes to the Library (as Save to Library does it, but
    keeping its read state, which is the app's to change) and onto the Shortlist, out of the Archive if
    it was there. Unstarred, its Library copy comes off the Shortlist and stays in the Library."""
    for r in rows:
        if bool(r["starred"]) == on:
            continue
        c.execute("UPDATE docs SET starred = ? WHERE id = ?", (1 if on else 0, r["id"]))
        if not r["url"]:
            continue
        try:
            if on:
                new_id = reader.save_to_library(c, r["id"])
                c.execute("UPDATE docs SET status = ? WHERE id = ? AND status != 'deleted'", (r["status"], r["id"]))
                if (c.execute("SELECT status FROM docs WHERE id = ?", (new_id,)).fetchone() or [""])[0] == "archive":
                    reader.set_status(c, new_id, "inbox")
                reader.set_starred(c, new_id, True)
            else:
                for lid in _library_copies(c, r["url"]):
                    reader.set_starred(c, lid, False)
                c.execute("UPDATE docs SET starred = 0 WHERE id = ?", (r["id"],))
        except Exception:  # noqa: BLE001 - the star itself is kept; the Library can be saved to from Daf
            log.exception("the Shortlist for %s", r["id"])


def _label(s):
    s = _norm(s)
    return " ".join(s[len(LABEL):].split())[:80] if s.startswith(LABEL) else None


def _public(url):
    from .kindlesend import _public as public
    host = urllib.parse.urlsplit(url).hostname
    return bool(host) and public(host)


def _follow(c, url, folder):
    """Follow a feed or a site: (stream id, its title, its feed's address)."""
    if feedsrc.daf():
        from .sources import rss
        return rss.follow(url, folder, conn=c)
    title = feedsrc.get().subscribe(url, folder, conn=c)
    return "feed/" + url, title, url


def _subscription_edit(c, P):
    action = P.get("ac")
    streams, titles = P.all("s"), P.all("t")
    if action not in ("subscribe", "unsubscribe", "edit") or not streams:
        _bad()
    add, remove = _label(P.get("a")), _label(P.get("r"))
    folder = add if add is not None else ("" if remove is not None else None)
    for i, s in enumerate(streams):
        if not s.startswith("feed/"):
            continue
        title = " ".join((titles[i] if i < len(titles) else "").split())[:200] or None
        fid = _feed_id(c, s)
        if action == "subscribe":
            url = re.sub(r"^(feed/)+", "", s)
            if fid and not url.isdigit() and c.execute("SELECT 1 FROM feeds WHERE id = ?", (fid,)).fetchone():
                reader.edit_feed(c, fid, title, folder)          # followed already: only moved or renamed
                continue
            if url.isdigit():
                continue                                          # FreshRSS skips these too
            if not re.match(r"^https?://\S+$", url) or not _public(url):
                _bad()
            try:
                fid, name, _ = _follow(c, url, folder or None)
            except Exception as e:  # noqa: BLE001
                log.warning("subscribe from an app: %s", e)
                _bad()
            if title and title != name:
                reader.edit_feed(c, fid, title, None)
        elif not fid:
            _bad()
        elif action == "unsubscribe":
            reader.unfollow_feed(c, fid)
        else:
            try:
                reader.edit_feed(c, fid, title, folder)
            except KeyError:
                _bad()
    return _text("OK")


def _quickadd(c, P):
    url = re.sub(r"^feed/", "", P.get("quickadd").strip())
    if not re.match(r"^https?://\S+$", url):
        return _json({"numResults": 0, "error": "A link starting with http:// or https://, please"})
    if not _public(url):
        return _json({"numResults": 0, "error": "Daf only follows public addresses from an app"})
    try:
        fid, name, feed_url = _follow(c, url, None)
    except Exception as e:  # noqa: BLE001
        return _json({"numResults": 0, "error": str(e)[:200]})
    return _json({"numResults": 1, "query": feed_url, "streamId": fid, "streamName": name})


def _export(c):
    subs = _subs(c)
    by = {}
    for x in subs:
        by.setdefault(x.get("folder") or "", []).append(x)
    a = lambda s: html.escape(str(s or ""), quote=True)  # noqa: E731
    line = lambda x, pad: (f'{pad}<outline type="rss" text="{a(x["title"])}" title="{a(x["title"])}" '  # noqa: E731
                           f'xmlUrl="{a(x["url"])}" htmlUrl="{a(x.get("site"))}"/>')
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
           f'<head><title>Daf</title><dateCreated>{time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())}</dateCreated></head>', "<body>"]
    for folder in sorted(by, key=lambda f: (f == "", f.casefold())):
        if folder:
            out.append(f'<outline text="{a(folder)}" title="{a(folder)}">')
            out += [line(x, "\t") for x in sorted(by[folder], key=lambda x: x["title"].casefold())]
            out.append("</outline>")
        else:
            out += [line(x, "") for x in sorted(by[folder], key=lambda x: x["title"].casefold())]
    out += ["</body>", "</opml>", ""]
    return Response("\n".join(out).encode(), headers={**HEADERS, "Content-Disposition": 'attachment; filename="daf-feeds.opml"'},
                    media_type="application/xml; charset=UTF-8")


def _usec(ts):
    """mark-all-as-read's ts: microseconds as Google sent it, but some apps send seconds, milliseconds or
    nanoseconds; 0 is now."""
    if ts <= 0:
        return int(time.time() * 1_000_000)
    return ts * 1_000_000 if ts < 10 ** 11 else ts * 1000 if ts < 10 ** 14 else ts if ts < 10 ** 17 else ts // 1000


def _folder_feeds(c, name):
    return [x for x in _subs(c) if (x.get("folder") or "") == name]


def _rename_tag(c, P):
    old, new = _label(P.get("s")), _label(P.get("dest"))
    if not old or not new:
        _bad()
    feeds = _folder_feeds(c, old)
    if not feeds and not c.execute("SELECT 1 FROM docs WHERE where_ = 'feed' AND category = ? LIMIT 1", (old,)).fetchone():
        _bad()
    for x in feeds:
        reader.edit_feed(c, x["id"], None, new)
    c.execute("UPDATE docs SET category = ? WHERE where_ = 'feed' AND category = ?", (new, old))
    return _text("OK")


def _disable_tag(c, P):
    for s in P.all("s"):
        name = _label(s)
        if not name:
            _bad()
        feeds = _folder_feeds(c, name)
        if not feeds and not c.execute("SELECT 1 FROM docs WHERE where_ = 'feed' AND category = ? LIMIT 1", (name,)).fetchone():
            _bad()
        for x in feeds:
            reader.edit_feed(c, x["id"], None, "")
        c.execute("UPDATE docs SET category = '' WHERE where_ = 'feed' AND category = ?", (name,))
    return _text("OK")


def _unread_count(c, exp):
    subs = _subs(c)
    rows = c.execute(f"SELECT d.feed, d.category, SUM({UNREAD_SQL}) AS n, MAX(g.gid) AS newest FROM docs d JOIN greader_ids g ON g.doc = d.id "
                     f"WHERE {_visible()} GROUP BY d.feed, d.category", (exp,)).fetchall()
    feeds, labels = {}, {}
    for r in rows:
        for key, box in ((r["feed"], feeds), (r["category"], labels)):
            if key:
                n, newest = box.get(key, (0, 0))
                box[key] = (n + (r["n"] or 0), max(newest, r["newest"] or 0))
    out, total, newest_all = [], 0, 0
    for x in subs:
        n, newest = feeds.get(x["id"], (0, 0))
        out.append({"id": x["id"], "count": n, "newestItemTimestampUsec": str(newest)})
    for name in sorted({x.get("folder") or "" for x in subs} | set(labels), key=str.casefold):
        if name:
            n, newest = labels.get(name, (0, 0))
            out.append({"id": LABEL + name, "count": n, "newestItemTimestampUsec": str(newest)})
    for n, newest in feeds.values():
        total, newest_all = total + n, max(newest_all, newest)
    out.append({"id": READING, "count": total, "newestItemTimestampUsec": str(newest_all)})
    return _json({"max": total, "unreadcounts": out})


def _picture(parts):
    """A feed's icon or a post's picture, by its signed address (no token: apps fetch these as plain images)."""
    if len(parts) != 4:
        _bad()
    kind, sig, name = parts[1], parts[2], parts[3]
    key, _ = _key()
    ok = re.fullmatch(r"[0-9a-f]{6,40}" if kind == "icon" else r"[0-9a-f]{16}", name)
    if not key or not ok or not hmac.compare_digest(sig.encode(), _mac(key, kind + "|" + name)[:32].encode()):
        raise _Stop(_text("Not Found!", 404))
    try:
        if kind == "icon":
            data, ctype = feedsrc.get().icon(name)
        else:
            from . import pages
            data, ctype = (pages.THUMBS / (name + ".jpg")).read_bytes(), "image/jpeg"
    except Exception:  # noqa: BLE001
        raise _Stop(_text("Not Found!", 404))
    return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=86400",
                                                      "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox"})


def _route(request, rest, body):
    path = "/" + rest.lstrip("/")
    while (m := re.match(r"^/(api|greader\.php)(?=/|$)", path)):     # an address given twice, as FreshRSS forgives it
        path = path[m.end():]
    P = _Params(request, body)
    if path in ("", "/"):
        return _text("OK")
    parts = path.split("/")
    if len(parts) < 3:
        _bad()
    if parts[1] == "check" and parts[2] == "compatibility":
        return _text("PASS" if re.search(r"GoogleLogin\s+auth=\S", request.headers.get("authorization", ""), re.I)
                     else "FAIL get HTTP Authorization header! Wrong Web server configuration.")
    if parts[1] in ("icon", "pic"):
        return _picture(parts)
    if parts[1] == "accounts":
        if parts[2] != "ClientLogin":
            _bad()
        from .app import client_ip
        ip = client_ip(request)
        if _throttled(ip):
            return _text("Too many tries. Wait 15 minutes.", 429)
        name, pw = P.get("Email", None), P.get("Passwd", None)
        if name is None or pw is None:
            _bad()
        if not check_login(name, pw):
            _failed(ip)
            _unauthorized()
        _succeeded(ip)
        tok = auth_token()
        return _text(f"SID={tok}\nLSID=null\nAuth={tok}\n")
    if parts[1:4] != ["reader", "api", "0"] or len(parts) < 5:
        _bad()
    m = re.search(r"GoogleLogin\s+auth=([^\s&,]+)", request.headers.get("authorization", ""), re.I)
    if not token_ok(m.group(1) if m else ""):
        _unauthorized()
    _touch()
    ep, more = parts[4], parts[5:]
    if ep == "token":
        return _text(edit_token() + "\n")
    if ep == "user-info":
        name = auth.username()
        return _json({"userId": name, "userName": name, "userProfileId": name, "userEmail": ""})
    if ep in ("edit-tag", "rename-tag", "disable-tag", "mark-all-as-read"):
        if request.method != "POST":
            _bad()
        t = P.get("T").strip()
        if t not in ("", "x") and not hmac.compare_digest(t.encode(), edit_token().encode()):
            _unauthorized()
    c = db.connect()
    try:
        out = _endpoint(c, request, P, ep, more)
        c.commit()
        return out
    finally:
        c.close()


def _endpoint(c, request, P, ep, more):
    settings = config.load_settings()
    exp = reader.expired_before(settings)
    if ep == "tag" and more[:1] == ["list"]:
        folders = sorted({x.get("folder") or "" for x in _subs(c)} - {""}, key=str.casefold)
        return _json({"tags": [{"id": STARRED}, {"id": READING}] + [{"id": LABEL + f, "type": "folder"} for f in folders]})
    if ep == "subscription" and more:
        if more[0] == "list":
            base = _base(request)
            return _json({"subscriptions": [
                {"id": x["id"], "title": _plain(x.get("title") or x.get("url") or x["id"]),
                 "categories": [{"id": LABEL + x["folder"], "label": x["folder"]}] if x.get("folder") else [],
                 "url": x.get("url") or "", "htmlUrl": x.get("site") or "",
                 "iconUrl": _signed(base, "icon", x["icon"]) if x.get("icon") and re.fullmatch(r"[0-9a-f]{6,40}", x["icon"]) else ""}
                for x in _subs(c)]})
        if more[0] == "export":
            return _export(c)
        if more[0] == "edit":
            return _subscription_edit(c, P)
        if more[0] == "quickadd":
            return _quickadd(c, P)
        _bad()
    if ep == "unread-count":
        _assign(c)
        return _unread_count(c, exp)
    if ep == "stream" and more:
        _assign(c)
        if more[0] == "contents":
            stream = "/".join(more[1:]) or P.get("s") or READING
            where, args, asc = _filters(c, stream, P, exp)
            n = _count(P, MAX_ITEMS)
            rows = c.execute(f"SELECT {FIELDS} FROM docs d JOIN greader_ids g ON g.doc = d.id WHERE {' AND '.join(where)} "
                             f"ORDER BY g.gid {'ASC' if asc else 'DESC'} LIMIT ?", (*args, n)).fetchall()
            out = {"id": READING, "updated": int(time.time()), "items": _items(c, request, rows, exp)}
            if rows and len(rows) >= n:
                out["continuation"] = str(rows[-1]["gid"])
            return _json(out)
        if more[:2] == ["items", "ids"]:
            stream = P.get("s")
            if not stream:
                _bad()
            where, args, asc = _filters(c, stream, P, exp)
            n = _count(P, MAX_IDS)
            ids = [r[0] for r in c.execute(f"SELECT g.gid FROM docs d JOIN greader_ids g ON g.doc = d.id WHERE {' AND '.join(where)} "
                                           f"ORDER BY g.gid {'ASC' if asc else 'DESC'} LIMIT ?", (*args, n))]
            out = {"itemRefs": [{"id": str(i)} for i in ids]}
            if ids and len(ids) >= n:
                out["continuation"] = str(ids[-1])
            return _json(out)
        if more[:2] == ["items", "contents"]:
            wanted = [parse_id(i) for i in P.all("i")[:MAX_ITEMS]]
            rows = sorted(_rows(c, wanted), key=lambda r: r["gid"], reverse=P.get("r") != "o")
            return _json({"id": READING, "updated": int(time.time()), "items": _items(c, request, rows, exp)})
        _bad()
    if ep == "edit-tag":
        _assign(c)
        rows = _rows(c, [parse_id(i) for i in P.all("i")[:10_000]])
        adds, removes = [_norm(x) for x in P.all("a")], [_norm(x) for x in P.all("r")]
        if READ in adds:
            _read(c, rows, True)
        elif READ in removes:
            _read(c, rows, False)
        if STARRED in adds:
            _star(c, rows, True)
        elif STARRED in removes:
            _star(c, rows, False)
        return _text("OK")             # labels on items, "like", "broadcast" and "kept-unread": not Daf's, as in FreshRSS
    if ep == "mark-all-as-read":
        _assign(c)
        ts = P.get("ts").strip() or "0"
        if not ts.isdigit():
            _bad()
        s = P.get("s").strip()
        e, a = _scope(c, s, exp) if s else ("0", [])
        name = _label(s)
        if e == "0" or (name is not None and not _folder_feeds(c, name)
                        and not c.execute("SELECT 1 FROM docs WHERE where_ = 'feed' AND category = ? LIMIT 1", (name,)).fetchone()):
            _bad()                     # a feed or a folder Daf hasn't, as FreshRSS answers it
        rows = c.execute(f"SELECT {FIELDS} FROM docs d JOIN greader_ids g ON g.doc = d.id WHERE {_visible()} AND ({e}) "
                         "AND d.status = 'unseen' AND g.gid <= ?", (*a, _usec(int(ts)))).fetchall()
        _read(c, rows, True)
        return _text("OK")
    if ep == "rename-tag":
        return _rename_tag(c, P)
    if ep == "disable-tag":
        return _disable_tag(c, P)
    _bad()


def _answer(request, rest, body):
    try:
        return _route(request, rest, body)
    except _Stop as s:
        return s.response
    except Exception:  # noqa: BLE001
        log.exception("greader.php %s", rest[:60])
        return _text("Internal Server Error!", 500)


async def greader(request: Request, rest: str = ""):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=HEADERS)
    body = b""
    if request.method == "POST":
        async for chunk in request.stream():
            body += chunk
            if len(body) > MAX_BODY:
                return _text("Request Entity Too Large!", 413)
    return await run_in_threadpool(_answer, request, rest, body)


# ---------------------------------------------------------------- Preferences → Reader apps

def _card(request, **more):
    """The card's facts: where an app connects, as whom, and the password's dates (never the password,
    but the once it's made)."""
    server = (config.load_settings().get("public_url") or _base(request)).rstrip("/")
    out = {"user": auth.username(), "server": server, "api": server + "/api/greader.php", **status(), **more}
    return Response(json.dumps(out), media_type="application/json", headers={"Cache-Control": "no-store"})


def router():
    """The routes, for app.py to include at its end (the card's use its user)."""
    from .app import user
    r = APIRouter()
    r.add_api_route("/api/greader.php", greader, methods=["GET", "POST", "OPTIONS"])
    r.add_api_route("/api/greader.php/{rest:path}", greader, methods=["GET", "POST", "OPTIONS"])

    @r.get("/api/greader", dependencies=[Depends(user)])
    def get_card(request: Request):
        return _card(request)

    @r.post("/api/greader/password", dependencies=[Depends(user)])
    def post_password(request: Request):
        return _card(request, password=make_password())

    @r.delete("/api/greader/password", dependencies=[Depends(user)])
    def delete_password(request: Request):
        remove_password()
        return _card(request)

    return r
