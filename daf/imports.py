"""Bringing a library over from another app: Preferences → Import. Drop the export file and Daf
tells which app it came from, shows what's in it, and then works through it in the background.

Links go to the Library the way a link you add does (Karakeep keeps the page; pages.py), keeping
when you saved them, whether they were read (archive), starred (the Shortlist) and their tags.
Highlights come along as Daf highlights, found in the text by their words, as the browser
extension's are; an export that has the article itself (Omnivore, Wallabag) gives Daf its text
too, which matters for pages that are gone. Feeds (OPML) go to FreshRSS, into their folders.

What each app exports (October 2026):
- Instapaper: Settings → Export → CSV (URL, Title, Selection, Folder, Timestamp, Tags). No highlights.
- Readwise Reader: Preferences → Export → "Export library" CSV (Title, URL, Document tags, Saved date,
  Location…). Highlights come through Readwise itself (sources/readwise.py reads the vault's).
- Raindrop.io: Settings → Backups, CSV (url, title, note, excerpt, folder, tags, created, highlights, favorite).
- GoodLinks: Settings → Export, JSON (url, title, tags, starred, addedAt, readAt, highlights).
- Wallabag: Export → JSON, with the article's HTML and its annotations.
- Pocket (closed July 2025): the export it emailed, a zip of CSV parts (title, url, time_added, tags,
  status) or the older ril_export.html.
- Omnivore (closed November 2024): the export zip (metadata_*.json, content/*.html, highlights/*.md).
- Any browser, Pinboard and others: bookmarks as HTML (the Netscape file).
- Any feed reader (Feedly, Feedbin, Inoreader, NetNewsWire): OPML.
- Anything else: a CSV or JSON with a url column (title, tags, status and date when it has them).
"""
import ast
import csv
import hashlib
import io
import json
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime
from html.parser import HTMLParser

from . import config, db, pages, reader, review, vaultnotes
from .sources import freshrss, karakeep

MAX_BYTES = 80 * 1024 * 1024
LABELS = {"instapaper": "Instapaper", "pocket": "Pocket", "omnivore": "Omnivore", "readwise": "Readwise Reader",
          "raindrop": "Raindrop.io", "goodlinks": "GoodLinks", "wallabag": "Wallabag", "bookmarks": "Bookmarks",
          "csv": "A list of links", "opml": "Feeds (OPML)"}


class NotAnExport(ValueError):
    pass


# ---- reading the files --------------------------------------------------------

def _epoch(v):
    """A date in any of the shapes exports use: epoch seconds or milliseconds, ISO, or 'YYYY-MM-DD HH:MM:SS'."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or re.fullmatch(r"\d+(\.\d+)?", str(v).strip()):
        n = float(v)
        n = n / 1000 if n > 1e11 else n
        return int(n) if 0 < n < 4e9 else None
    s = str(v).strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", s)            # +0000 → +00:00
    for f in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return int((datetime.fromisoformat(s) if f is None else datetime.strptime(s, f)).timestamp())
        except ValueError:
            continue
    return None


def _tags(v):
    if not v:
        return []
    if isinstance(v, list):
        out = [x.get("name") if isinstance(x, dict) else x for x in v]
    else:
        s = str(v).strip()
        out = None
        if s[:1] == "[":
            for load in (json.loads, ast.literal_eval):
                try:
                    out = load(s)
                    break
                except (ValueError, SyntaxError):
                    continue
        if out is None:
            out = re.split(r"[|,]", s)
    seen, tags = set(), []
    for t in out:
        t = " ".join(str(t or "").split()).strip("#").strip()[:40]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    return tags[:12]


def _link(url, title=None, **kw):
    url = str(url or "").strip()
    if not re.match(r"^https?://\S+$", url) or len(url) > 4000:
        return None
    return {"url": url, "title": " ".join(str(title or "").split())[:300] or None, "tags": kw.get("tags") or [],
            "status": kw.get("status") or "inbox", "starred": bool(kw.get("starred")), "added": kw.get("added"),
            "highlights": [h for h in kw.get("highlights") or [] if (h.get("text") or "").strip()], "html": kw.get("html") or None}


def _hl(text, note=None, created=None):
    return {"text": str(text or "").strip()[:10000], "note": (str(note).strip() or None) if note else None, "created": _epoch(created)}


def _csv_rows(text):
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{(k or "").strip().lower(): (v or "").strip() if isinstance(v, str) else v for k, v in r.items()} for r in rows]


def _instapaper(rows):
    out = []
    for r in rows:
        folder = r.get("folder") or ""
        status = "archive" if folder.lower() == "archive" else "inbox"
        tags = _tags(r.get("tags"))
        if folder and folder.lower() not in ("unread", "archive", "starred"):
            tags = _tags(tags + [folder])
        out.append(_link(r.get("url"), r.get("title"), status=status, starred=folder.lower() == "starred", tags=tags, added=_epoch(r.get("timestamp"))))
    return out


def _pocket_csv(rows):
    return [_link(r.get("url"), r.get("title"), status="archive" if (r.get("status") or "").lower() in ("archive", "read") else "inbox",
                  tags=_tags(r.get("tags")), added=_epoch(r.get("time_added"))) for r in rows]


def _readwise(rows):
    out = []
    for r in rows:
        loc = (r.get("location") or "").lower()
        if loc == "feed":                    # Reader's feed items were never saved
            continue
        out.append(_link(r.get("url"), r.get("title"), status={"archive": "archive", "later": "later", "shortlist": "later"}.get(loc, "inbox"),
                         starred=loc == "shortlist", tags=_tags(r.get("document tags")), added=_epoch(r.get("saved date"))))
    return out


def _raindrop(rows):
    out = []
    for r in rows:
        hls, cur = [], None
        for line in (r.get("highlights") or "").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("highlight:"):
                cur = _hl(line.split(":", 1)[1])
                hls.append(cur)
            elif line.lower().startswith("note:") and cur:
                cur["note"] = line.split(":", 1)[1].strip() or None
            else:
                cur = _hl(line)
                hls.append(cur)
        folder = r.get("folder") or ""
        tags = _tags(r.get("tags"))
        if folder and folder.lower() not in ("unsorted", "trash"):
            tags = _tags(tags + [folder.split("/")[-1]])
        if folder.lower() == "trash":
            continue
        out.append(_link(r.get("url"), r.get("title"), tags=tags, starred=(r.get("favorite") or "").lower() == "true",
                         added=_epoch(r.get("created")), highlights=hls))
    return out


STATUS_WORDS = re.compile(r"archiv|read|done|finished", re.I)


def _generic(rows):
    def pick(r, *keys):
        for k in keys:
            if r.get(k):
                return r[k]
        return None
    out = []
    for r in rows:
        st = str(pick(r, "status", "state", "location", "folder") or "")
        unread = re.search(r"unread|inbox|new|later", st, re.I)
        out.append(_link(pick(r, "url", "link", "href", "uri"), pick(r, "title", "name"), tags=_tags(pick(r, "tags", "labels", "tag")),
                         status="archive" if st and STATUS_WORDS.search(st) and not unread else "later" if re.search("later", st, re.I) else "inbox",
                         starred=str(pick(r, "starred", "favorite", "favourite", "is_starred") or "").lower() in ("1", "true", "yes"),
                         added=_epoch(pick(r, "time_added", "added", "saved", "saved date", "created", "created_at", "date", "timestamp"))))
    return out


def _goodlinks(data):
    return [_link(x.get("url"), x.get("title"), tags=_tags(x.get("tags")), starred=x.get("starred"),
                  status="archive" if x.get("readAt") else "inbox", added=_epoch(x.get("addedAt")),
                  highlights=[_hl(h.get("content"), h.get("note"), h.get("time")) for h in x.get("highlights") or []])
            for x in data if isinstance(x, dict)]


def _wallabag(data):
    return [_link(x.get("url") or x.get("given_url"), x.get("title"), tags=_tags(x.get("tags")), starred=x.get("is_starred"),
                  status="archive" if x.get("is_archived") else "inbox", added=_epoch(x.get("created_at")), html=x.get("content"),
                  highlights=[_hl(a.get("quote"), a.get("text"), a.get("created_at")) for a in x.get("annotations") or []])
            for x in data if isinstance(x, dict)]


def _omnivore_highlights(md):
    out, cur = [], None
    for block in re.split(r"\n\s*\n", md or ""):
        b = block.strip()
        if not b:
            continue
        if b.startswith(">"):
            q = "\n".join(re.sub(r"^>\s?", "", line) for line in b.splitlines())
            q = re.sub(r"\s*\[⤴️?\]\([^)]*\)\s*$", "", q).strip()
            cur = _hl(q)
            out.append(cur)
        elif cur:
            cur["note"] = ((cur["note"] + "\n\n") if cur["note"] else "") + b
    return out


def _omnivore(z):
    names = z.namelist()
    items = []
    for n in sorted(x for x in names if re.search(r"(^|/)metadata_.*\.json$", x)):
        for x in json.loads(z.read(n).decode("utf-8-sig")):
            state = str(x.get("state") or "").upper()
            if state == "DELETED":
                continue
            slug = x.get("slug") or ""
            html = hl = None
            for p in names:
                if p.endswith(f"content/{slug}.html"):
                    html = z.read(p).decode("utf-8", "replace")
                elif p.endswith(f"highlights/{slug}.md"):
                    hl = z.read(p).decode("utf-8", "replace")
            items.append(_link(x.get("url") or x.get("originalUrl"), x.get("title"), tags=_tags(x.get("labels")),
                               status="archive" if state == "ARCHIVED" or x.get("archivedAt") else "inbox",
                               added=_epoch(x.get("savedAt")), html=html, highlights=_omnivore_highlights(hl)))
    return items


class _Bookmarks(HTMLParser):
    """The Netscape bookmark file: browsers, Pinboard, Raindrop, and Pocket's old ril_export.html
    (whose <h1>Read Archive</h1> section is what you'd read)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items, self.folders, self.pending, self.a, self.text, self.archive = [], [], None, None, "", False
        self.h = None

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        if tag in ("h1", "h3"):
            self.h, self.text = tag, ""
        elif tag == "dl":
            self.folders.append(self.pending)
            self.pending = None
        elif tag == "a":
            self.a, self.text = at, ""

    def handle_endtag(self, tag):
        if tag == "h1" and self.h == "h1":
            self.archive = "archive" in self.text.lower() or "read" == self.text.strip().lower()
            self.h = None
        elif tag == "h3" and self.h == "h3":
            self.pending = self.text.strip()
            self.h = None
        elif tag == "dl" and self.folders:
            self.folders.pop()
        elif tag == "a" and self.a is not None:
            a = self.a
            folder = next((f for f in reversed(self.folders) if f), None)
            tags = _tags(a.get("tags"))
            if folder and folder.lower() not in ("bookmarks", "bookmarks bar", "bookmarks menu", "bookmarks toolbar", "other bookmarks",
                                                 "favorites", "favourites", "unsorted"):
                tags = _tags(tags + [folder])
            self.items.append(_link(a.get("href"), self.text, tags=tags, added=_epoch(a.get("add_date") or a.get("time_added")),
                                    status="archive" if self.archive or a.get("toread") == "0" else "inbox"))
            self.a = None

    def handle_data(self, data):
        if self.h or self.a is not None:
            self.text += data


class _Opml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.feeds, self.stack = [], []

    def handle_starttag(self, tag, attrs):
        if tag != "outline":
            return
        at = {k.lower(): v for k, v in attrs}
        url = at.get("xmlurl")
        if url:
            folder = next((f for f in reversed(self.stack) if f), None)
            self.feeds.append({"feed": url, "title": at.get("title") or at.get("text") or url, "folder": folder})
        self.stack.append(None if url else (at.get("title") or at.get("text") or None))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "outline":
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag == "outline" and self.stack:
            self.stack.pop()


def detect(name, data):
    """(service, items) for an export file. Raises NotAnExport when it isn't one Daf knows."""
    if len(data) > MAX_BYTES:
        raise NotAnExport("That file is bigger than Daf takes (80 MB).")
    if data[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise NotAnExport("That zip file is damaged.")
        names = z.namelist()
        if any(re.search(r"(^|/)metadata_.*\.json$", n) for n in names):
            return "omnivore", _omnivore(z)
        parts = [n for n in names if n.lower().endswith(".csv")]
        if parts:
            rows = []
            for n in sorted(parts):
                rows += _csv_rows(z.read(n).decode("utf-8-sig", "replace"))
            return _from_rows(rows)
        if any(n.lower().endswith(".html") for n in names):
            n = next(n for n in names if n.lower().endswith(".html"))
            return detect(n, z.read(n))
        raise NotAnExport("Daf doesn't know what's in that zip.")
    text = data.decode("utf-8-sig", "replace")
    head = text[:4000].lower()
    if "<opml" in head:
        p = _Opml()
        p.feed(text)
        return "opml", p.feeds
    if "netscape-bookmark-file" in head or ("<a " in head and "href=" in head and "<html" not in head[:200] and "<dl" in head) or "pocket export" in head:
        p = _Bookmarks()
        p.feed(text)
        return ("pocket" if "pocket export" in head or "read archive" in text.lower() else "bookmarks"), p.items
    stripped = text.lstrip()
    if stripped[:1] in "[{":
        try:
            data = json.loads(text)
        except ValueError:
            raise NotAnExport("That JSON file is damaged.")
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [])
        first = next((x for x in data if isinstance(x, dict)), {})
        if "addedAt" in first or "readAt" in first:
            return "goodlinks", _goodlinks(data)
        if "is_archived" in first or "annotations" in first:
            return "wallabag", _wallabag(data)
        if any(k in first for k in ("url", "link", "href")):
            return "csv", _generic([{str(k).lower(): v for k, v in x.items()} for x in data if isinstance(x, dict)])
        raise NotAnExport("Daf doesn't know that JSON file.")
    if name.lower().endswith((".csv", ".txt")) or "," in text[:500]:
        return _from_rows(_csv_rows(text))
    raise NotAnExport("Daf doesn't know that kind of file. It takes CSV, JSON, HTML bookmarks, OPML and zip exports.")


def _from_rows(rows):
    if not rows:
        raise NotAnExport("That file has no rows.")
    keys = set(rows[0].keys())
    if {"url", "title", "selection", "folder"} <= keys:
        return "instapaper", _instapaper(rows)
    if {"title", "url", "time_added"} <= keys:
        return "pocket", _pocket_csv(rows)
    if {"title", "url", "location"} <= keys and ("saved date" in keys or "document tags" in keys):
        return "readwise", _readwise(rows)
    if {"url", "title", "excerpt", "folder"} <= keys:
        return "raindrop", _raindrop(rows)
    if keys & {"url", "link", "href", "uri"}:
        return "csv", _generic(rows)
    raise NotAnExport("That CSV has no column of links (url).")


# ---- what's in it, and bringing it in ------------------------------------------

def summary(service, items):
    if service == "opml":
        folders = sorted({f["folder"] for f in items if f.get("folder")})
        return {"service": service, "label": LABELS[service], "feeds": len(items), "folders": folders[:20],
                "sample": [f["title"] for f in items[:6]]}
    st = {"inbox": 0, "later": 0, "archive": 0}
    for x in items:
        st[x["status"]] = st.get(x["status"], 0) + 1
    return {"service": service, "label": LABELS.get(service, service), "links": len(items), "status": st,
            "starred": sum(1 for x in items if x["starred"]), "tagged": sum(1 for x in items if x["tags"]),
            "highlights": sum(len(x["highlights"]) for x in items), "with_text": sum(1 for x in items if x["html"]),
            "sample": [x["title"] or x["url"] for x in items[:6]]}


def create(conn, name, data):
    """Reads the file and keeps what's in it, ready to start. Returns its summary with its id."""
    service, items = detect(name or "", data)
    items = [x for x in items if x]
    if service != "opml":                                   # one of each link, the last mention winning
        seen = {}
        for x in items:
            seen[pages.norm_url(x["url"])] = x
        items = list(seen.values())
        items.sort(key=lambda x: x["added"] or 0)          # oldest first, so the Library's order matches
    if not items:
        raise NotAnExport("Nothing in that file looks like a link Daf can save.")
    iid = uuid.uuid4().hex[:12]
    conn.execute("INSERT INTO imports (id, service, name, created, items, state) VALUES (?, ?, ?, ?, ?, 'ready')",
                 (iid, service, (name or "")[:200], int(time.time()), json.dumps(items)))
    return {"id": iid, **summary(service, items)}


_summaries = {}                   # an import's items never change: what's in it is worked out once


def get(conn, iid):
    r = conn.execute("SELECT id, service, name, created, state, pos, added, had, skipped, failed, finished, highlights, opts, errors "
                     "FROM imports WHERE id = ?", (iid,)).fetchone()
    if not r:
        return None
    if iid not in _summaries:
        items = json.loads(conn.execute("SELECT items FROM imports WHERE id = ?", (iid,)).fetchone()[0])
        _summaries[iid] = dict(summary(r["service"], items), total=len(items))
    out = {k: r[k] for k in ("id", "service", "name", "created", "state", "pos", "added", "had", "skipped", "failed", "finished")}
    out.update(_summaries[iid])                    # "highlights" there is how many the file has
    out["hl_added"] = r["highlights"]
    out["opts"] = json.loads(r["opts"] or "{}")
    out["errors"] = json.loads(r["errors"] or "[]")
    return out


def listing(conn):
    return [get(conn, r[0]) for r in conn.execute("SELECT id FROM imports ORDER BY created DESC LIMIT 8")]


def _hl_id(doc_id, text):
    return "d" + hashlib.sha1(f"{doc_id}|q:{hashlib.sha1(text.encode()).hexdigest()[:12]}|None|{text}".encode()).hexdigest()[:16]


def _add_highlights(c, settings, doc_id, hls):
    """Highlights placed by their words ({q}), as the extension's. Ones already there stay as they are."""
    if not hls:
        return 0
    d = c.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    reader._ensure_book(c, d)
    have = {r[0].strip() for r in c.execute("SELECT text FROM highlights WHERE book_id = ? AND deleted = 0", (doc_id,)) if r[0]}
    n = 0
    for h in hls:
        text = h["text"].strip()
        if not text or text in have:
            continue
        hid = _hl_id(doc_id, text)
        c.execute("INSERT OR IGNORE INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted, color) "
                  "VALUES (?, ?, 'daf', ?, NULL, NULL, NULL, ?, ?, ?, 0, NULL)",
                  (hid, doc_id, text, int(h.get("created") or time.time()), json.dumps({"q": text}, ensure_ascii=False), int(time.time())))
        if h.get("note"):
            review.set_note(c, hid, h["note"])
            review.add_tags(c, hid, review.dot_tags(h["note"]))
        have.add(text)
        n += 1
    if n:
        vaultnotes.write_article(c, settings, doc_id)
    return n


def _one_link(c, settings, x, opts):
    """Returns (what happened, highlights added): added | had | skipped."""
    if x["status"] == "archive" and not opts.get("archived"):
        return "skipped", 0
    d = pages.find_doc(c, x["url"])
    if d and d["status"] != "deleted" and d["where_"] != "feed":
        return "had", _add_highlights(c, settings, d["id"], x["highlights"])
    doc_id, _ = pages.save_page(c, x["url"], x["title"], added=x["added"])
    row = c.execute("SELECT ext_id, where_ FROM docs WHERE id = ?", (doc_id,)).fetchone()
    own = not karakeep.writes()                   # Daf keeps the Library: status, star and tags are Daf's alone
    bid = row["ext_id"] if doc_id.startswith("kk:") and not own else None
    c.commit()                    # saved: the write lock isn't held while Karakeep is asked for the rest
    if x["status"] == "archive" and bid:
        karakeep.set_archived(bid, True)
    if x["starred"] and bid:
        karakeep.set_favourited(bid, True)
    if x["tags"] and bid:
        karakeep.attach_tags(bid, x["tags"])
    if x["status"] in ("archive", "later"):
        c.execute("UPDATE docs SET status = ? WHERE id = ?", (x["status"], doc_id))
    if x["starred"] and (bid or own):
        c.execute("UPDATE docs SET starred = 1 WHERE id = ?", (doc_id,))
    if x["tags"] and (bid or own):
        c.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(x["tags"]), doc_id))
    if x["html"]:
        pages.keep_text(c, doc_id, x["html"], x["url"], whole_page=False)
    return "added", _add_highlights(c, settings, doc_id, x["highlights"])


_feeds_have = {}


def _one_feed(c, x, opts):
    if "urls" not in _feeds_have or time.time() - _feeds_have.get("at", 0) > 600:
        _feeds_have.update(urls={pages.norm_url(s["url"]) for s in freshrss.subscriptions()}, at=time.time())
    if pages.norm_url(x["feed"]) in _feeds_have["urls"]:
        return "had", 0
    freshrss.subscribe(x["feed"], x.get("folder") if opts.get("folders", True) else None)
    _feeds_have["urls"].add(pages.norm_url(x["feed"]))
    return "added", 0


_running = {}
_lock = threading.Lock()


def start(conn, iid, opts):
    r = conn.execute("SELECT state FROM imports WHERE id = ?", (iid,)).fetchone()
    if not r:
        raise KeyError(iid)
    o = {"archived": bool((opts or {}).get("archived")), "folders": (opts or {}).get("folders") is not False}
    conn.execute("UPDATE imports SET state = 'running', opts = ? WHERE id = ?", (json.dumps(o), iid))
    conn.commit()
    _spawn(iid)


def stop(conn, iid):
    conn.execute("UPDATE imports SET state = 'stopped' WHERE id = ? AND state = 'running'", (iid,))


def _spawn(iid):
    with _lock:
        t = _running.get(iid)
        if t and t.is_alive():
            return
        t = threading.Thread(target=_work, args=(iid,), name=f"import-{iid}", daemon=True)
        _running[iid] = t
        t.start()


def _work(iid):
    import logging
    log = logging.getLogger("daf.imports")
    settings = config.load_settings()
    with db.session() as c:                       # the file's items, read once (an 80 MB export is slow to parse)
        r = c.execute("SELECT items FROM imports WHERE id = ?", (iid,)).fetchone()
    if not r:
        return
    items = json.loads(r["items"])
    while True:
        with db.session() as c:
            r = c.execute("SELECT service, opts, state, pos, errors FROM imports WHERE id = ?", (iid,)).fetchone()
            if not r or r["state"] != "running":
                return
            if r["pos"] >= len(items):
                c.execute("UPDATE imports SET state = 'done', finished = ? WHERE id = ?", (int(time.time()), iid))
                return
            x, opts = items[r["pos"]], json.loads(r["opts"] or "{}")
            try:
                what, n = _one_feed(c, x, opts) if r["service"] == "opml" else _one_link(c, settings, x, opts)
                c.execute(f"UPDATE imports SET pos = pos + 1, {what} = {what} + 1, highlights = highlights + ? WHERE id = ?", (n, iid))
            except Exception as e:  # noqa: BLE001 - one bad link doesn't stop the rest
                c.rollback()
                errs = (json.loads(r["errors"] or "[]") + [{"url": x.get("url") or x.get("feed"), "error": str(e)[:200]}])[-20:]
                c.execute("UPDATE imports SET pos = pos + 1, failed = failed + 1, errors = ? WHERE id = ?", (json.dumps(errs), iid))
                log.warning("import %s: %s: %s", iid, x.get("url") or x.get("feed"), e)
        time.sleep(0.25)


def resume():
    """From the sync loop: an import a restart stopped goes on."""
    with db.session() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM imports WHERE state = 'running'")]
    for iid in ids:
        _spawn(iid)
