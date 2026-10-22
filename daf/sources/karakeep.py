"""Karakeep through its REST API (http://127.0.0.1:3000/api/v1), and how much of the Library it
still keeps (settings.json library.karakeep, see mode()).

"on" is the old way: Karakeep keeps the saved copy; Daf lists it, reads its archived text, saves
new links and archives. "read" is the move to Daf keeping the Library itself (pages.py): Daf
writes nothing to Karakeep any more, and a bookmark made in Karakeep (its own extension or app)
still comes in, once. "off": Karakeep isn't asked anything. "Later" is Daf's own status either way.
"""
import json
import re
import time
import urllib.request

from .. import content, secrets

BASE = "http://127.0.0.1:3000/api/v1"


class KarakeepError(Exception):
    pass


def mode():
    """on | read | off (the module's docstring)."""
    from .. import config
    m = (config.load_settings().get("library") or {}).get("karakeep")
    return m if m in ("on", "read", "off") else "on"


def writes():
    """Karakeep still keeps the Library: Daf's changes go to it."""
    return mode() == "on"


def _req(method, path, body=None):
    key = secrets.karakeep_key()
    if not key:
        raise KarakeepError("no Karakeep API key")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise KarakeepError(f"Karakeep {e.code} on {method} {path.split('?')[0]}") from e


def asset_bytes(asset_id):
    req = urllib.request.Request(BASE + f"/assets/{asset_id}", headers={"Authorization": "Bearer " + (secrets.karakeep_key() or "")})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(80_000_000)


def kind_of(url, ctype):
    u = (url or "").lower()
    if "youtube.com/watch" in u or "youtu.be/" in u or "/watch?v=" in u:
        return "video"
    if re.search(r"//(www\.)?(x|twitter)\.com/", u):
        return "tweet"
    if ctype == "asset" or u.endswith(".pdf"):
        return "pdf"
    return "article"


def _epoch(s):
    if not s:
        return None
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def sync(conn):
    """List every bookmark. Returns how many. With Daf keeping the Library ("read"), only bookmarks
    Daf doesn't have yet come in, and nothing leaves; "off" asks nothing."""
    m = mode()
    if m == "off":
        return 0
    seen, cursor = [], None
    while True:
        d = _req("GET", "/bookmarks?limit=100" + (f"&cursor={cursor}" if cursor else ""))
        for b in d.get("bookmarks", []):
            c = b.get("content") or {}
            url = c.get("url") or c.get("sourceUrl") or ""
            title = (b.get("title") or c.get("title") or c.get("fileName") or url or "Saved item").strip()
            title = re.sub(r"\s+[|·–-]\s+[^|·–-]{2,40}$", "", title) if len(title) > 50 else title
            did = "kk:" + b["id"]
            kind = kind_of(url, c.get("type"))
            archived = bool(b.get("archived"))
            row = conn.execute("SELECT status FROM docs WHERE id = ?", (did,)).fetchone()
            if m == "read":
                seen.append(did)
                if row or _have_url(conn, url):
                    continue                  # Daf keeps it now: its status, tags and star are Daf's
            # Deleted in Daf stays deleted until purge_deleted takes it out of Karakeep too.
            status = "deleted" if row and row["status"] == "deleted" else "archive" if archived else \
                (row["status"] if row and row["status"] in ("inbox", "later") else "inbox")
            conn.execute(
                "INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, words, summary, ext_id, thumb, tags, starred) "
                "VALUES (?, ?, 'library', ?, ?, ?, ?, '', ?, ?, ?, NULL, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET kind = excluded.kind, status = excluded.status, "
                # A title Daf found inside a PDF beats Karakeep's file name.
                "title = CASE WHEN excluded.title LIKE '%.pdf' AND docs.title NOT LIKE '%.pdf' THEN docs.title ELSE excluded.title END, "
                "author = excluded.author, source = excluded.source, url = excluded.url, thumb = excluded.thumb, "
                "summary = COALESCE(docs.summary, excluded.summary), tags = excluded.tags, starred = excluded.starred",
                (did, kind, status, title, c.get("author") or "", c.get("publisher") or (re.sub(r"^https?://(www\.)?", "", url).split("/")[0]),
                 url, _epoch(c.get("datePublished")), _epoch(b.get("createdAt")), (c.get("description") or "")[:280],
                 b["id"], c.get("imageUrl"), json.dumps([t["name"] for t in b.get("tags") or [] if t.get("name")]) or None, 1 if b.get("favourited") else 0))
            seen.append(did)
        cursor = d.get("nextCursor")
        if not cursor:
            break
    if seen and m == "on":
        conn.execute(f"DELETE FROM docs WHERE where_ = 'library' AND id LIKE 'kk:%' AND id NOT IN ({','.join('?' * len(seen))}) "
                     "AND id NOT IN (SELECT DISTINCT book_id FROM highlights WHERE book_id IS NOT NULL)", seen)
    return len(seen)


def _have_url(conn, url):
    """A link Daf already keeps (saved in Daf while Karakeep had it too): not a second copy."""
    if not url:
        return False
    from ..pages import find_doc
    d = find_doc(conn, url)
    return bool(d and d["where_"] == "library")


def fetch_content(conn, doc_id):
    """The archived text of one bookmark, cleaned, cached in doc_content."""
    b = _req("GET", f"/bookmarks/{doc_id[3:]}?includeContent=true")
    c = b.get("content") or {}
    raw = c.get("htmlContent") or ""
    bl = content.blocks(raw)
    if not bl and c.get("description"):
        bl = [{"t": "p", "h": c["description"], "x": c["description"]}]
    if not bl:
        return bl            # Karakeep hasn't read the page yet: keep nothing, so the next open asks again
    conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (doc_id, json.dumps(bl), int(time.time())))
    conn.execute("UPDATE docs SET words = ?, summary = COALESCE(NULLIF(summary, ''), ?) WHERE id = ?",
                 (content.words(bl), content.summary(bl), doc_id))
    return bl


def save(url, title=None):
    body = {"type": "link", "url": url}
    if title:
        body["title"] = title
    return _req("POST", "/bookmarks", body)


def upload_pdf(name, data, title=None):
    """A PDF from your computer becomes a Karakeep bookmark of type asset (and then a Daf PDF)."""
    import uuid
    key = secrets.karakeep_key()
    if not key:
        raise KarakeepError("no Karakeep API key")
    b = "----daf" + uuid.uuid4().hex
    safe = name.replace('"', "'")
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{safe}"\r\nContent-Type: application/pdf\r\n\r\n').encode() + data + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(BASE + "/assets", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + key, "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            asset = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise KarakeepError(f"Karakeep {e.code} on the upload") from e
    return _req("POST", "/bookmarks", {"type": "asset", "assetType": "pdf", "assetId": asset["assetId"],
                                      "fileName": name, **({"title": title} if title else {})})


def set_favourited(bookmark_id, fav):
    if not writes():
        return {}
    return _req("PATCH", f"/bookmarks/{bookmark_id}", {"favourited": bool(fav)})


def attach_tags(bookmark_id, names):
    if not writes():
        return {}
    return _req("POST", f"/bookmarks/{bookmark_id}/tags", {"tags": [{"tagName": n} for n in names]})


def detach_tags(bookmark_id, names):
    if not writes():
        return {}
    return _req("DELETE", f"/bookmarks/{bookmark_id}/tags", {"tags": [{"tagName": n} for n in names]})


def delete(bookmark_id):
    if not writes():
        return {}
    return _req("DELETE", f"/bookmarks/{bookmark_id}")


def set_archived(bookmark_id, archived):
    if not writes():
        return {}
    return _req("PATCH", f"/bookmarks/{bookmark_id}", {"archived": bool(archived)})


# ---- Daf takes the Library over, once ------------------------------------------------------------

def _all(path, key):
    out, cursor = [], None
    while True:
        d = _req("GET", path + ("&" if "?" in path else "?") + "limit=100" + (f"&cursor={cursor}" if cursor else ""))
        out += d.get(key, [])
        cursor = d.get("nextCursor")
        if not cursor:
            return out


def take_over(conn, settings, say=print):
    """`daf karakeep-import`: everything of Karakeep's that Daf doesn't hold yet comes in, and from
    then on Daf keeps the Library ("read": Karakeep is only read, for bookmarks made there until its
    extension and app are swapped for Daf's). Safe to run again: it only fills what's missing.

    - every bookmark's row (a last sync the old way), its text, and its PDF when it is one;
    - its note (when Daf has none), Karakeep's summary (when Daf has no model summary);
    - its picture, kept on the server: Karakeep's own copy of the banner, else the page's picture;
    - its highlights, placed by their words in Daf's copy of the text;
    - Karakeep's lists, as tags of the same name."""
    from .. import imports, pages, pdfdoc
    n = {"bookmarks": sync(conn) if mode() == "on" else 0, "text": 0, "notes": 0, "summaries": 0, "pictures": 0,
         "highlights": 0, "list_tags": 0, "pdfs": 0}
    conn.commit()
    for b in _all("/bookmarks?includeContent=false", "bookmarks"):
        did = "kk:" + b["id"]
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (did,)).fetchone()
        if not d:
            continue
        c = b.get("content") or {}
        if (b.get("note") or "").strip() and not (d["note"] or "").strip():
            conn.execute("UPDATE docs SET note = ? WHERE id = ?", (b["note"].strip(), did))
            n["notes"] += 1
        if (b.get("summary") or "").strip() and not (d["ai_summary"] or "").strip():
            conn.execute("UPDATE docs SET ai_summary = ? WHERE id = ?", (b["summary"].strip(), did))
            n["summaries"] += 1
        if c.get("type") == "asset" and c.get("assetType") == "pdf":
            f = pdfdoc.path_for(did)
            if not f.exists():
                try:
                    data = asset_bytes(c["assetId"])
                    if data.startswith(b"%PDF"):
                        pdfdoc.DIR.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(data)
                        n["pdfs"] += 1
                except Exception as e:  # noqa: BLE001
                    say(f"  {did}: the PDF didn't come: {e}")
        elif not conn.execute("SELECT 1 FROM doc_content WHERE id = ? AND blocks NOT IN ('[]', '')", (did,)).fetchone():
            try:
                if fetch_content(conn, did):
                    n["text"] += 1
            except Exception as e:  # noqa: BLE001
                say(f"  {did}: no text from Karakeep: {e}")
        if not d["thumb"] or str(d["thumb"]).startswith("http"):
            banner = next((a["id"] for a in b.get("assets") or [] if a.get("assetType") == "bannerImage"), None) or c.get("imageAssetId")
            t = None
            if banner:
                try:
                    t = pages.keep_thumb_bytes(asset_bytes(banner))
                except Exception:  # noqa: BLE001
                    t = None
            if not t and c.get("imageUrl"):
                t = pages.keep_thumb(c["imageUrl"])
            if t:
                conn.execute("UPDATE docs SET thumb = ? WHERE id = ?", (t, did))
                n["pictures"] += 1
        conn.commit()
    by_doc = {}
    for h in _all("/highlights", "highlights"):
        by_doc.setdefault("kk:" + h["bookmarkId"], []).append({"text": h.get("text") or "", "note": h.get("note") or None,
                                                               "created": _epoch(h.get("createdAt"))})
    for did, hls in by_doc.items():
        if conn.execute("SELECT 1 FROM docs WHERE id = ?", (did,)).fetchone():
            n["highlights"] += imports._add_highlights(conn, settings, did, hls)
    for lst in _req("GET", "/lists").get("lists", []):
        name = " ".join((lst.get("name") or "").split())
        if not name:
            continue
        try:
            members = _all(f"/lists/{lst['id']}/bookmarks?includeContent=false", "bookmarks")
        except KarakeepError as e:
            say(f"  list {name}: {e}")
            continue
        for b in members:
            row = conn.execute("SELECT tags FROM docs WHERE id = ?", ("kk:" + b["id"],)).fetchone()
            if not row:
                continue
            tags = json.loads(row["tags"]) if row["tags"] else []
            if name.lower() not in {t.lower() for t in tags}:
                conn.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(tags + [name]), "kk:" + b["id"]))
                n["list_tags"] += 1
    from .. import config
    s = config.load_settings()
    s["library"] = {**(s.get("library") or {}), "karakeep": "read", "since": int(time.time())}
    config.save_settings(s)
    return n
