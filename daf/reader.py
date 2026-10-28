"""The reader: lists, documents, statuses, highlights on articles, reading time,
Ask, and read-aloud. The Feed is FreshRSS, the Library is Karakeep (sources/)."""
import hashlib
import json
import logging
import re
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config, today as T, vaultnotes
from .sources import freshrss, karakeep

log = logging.getLogger("daf.reader")
KIND_LABEL = {"article": "Article", "video": "Video", "tweet": "Tweet", "pdf": "PDF", "podcast": "Podcast"}
TTS_DIR = config.STATE / "tts"


def expired_before(settings):
    return int(time.time()) - int(settings.get("feed_expire_days", 30)) * 86400


def _hl_counts(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT book_id, COUNT(*) FROM highlights WHERE deleted = 0 AND source = 'daf' GROUP BY book_id")}


SORTS = {
    "new": "added DESC",
    "old": "added ASC",
    "published": "COALESCE(published, added) DESC",
    "short": "(COALESCE(duration / 60.0, words / 238.0) IS NULL), COALESCE(duration / 60.0, words / 238.0) ASC",
    "long": "(COALESCE(duration / 60.0, words / 238.0) IS NULL), COALESCE(duration / 60.0, words / 238.0) DESC",
    "progress": "(progress > 0 AND progress < 98) DESC, progress DESC, added DESC",
}


MINS = "(CASE WHEN duration THEN duration / 60.0 ELSE COALESCE(words, 0) / 238.0 END)"


def _filters(flt, args):
    """Readwise-style filters for a list: source, author, length in minutes, added within N days,
    highlighted, not started. Returns SQL to AND on, appending its args."""
    q = ""
    flt = flt or {}
    if flt.get("source"):
        q += " AND source = ?"
        args.append(str(flt["source"])[:200])
    if flt.get("author"):
        q += " AND author LIKE ?"
        args.append(f"%{str(flt['author'])[:100]}%")
    for k, op in (("minlen", ">="), ("maxlen", "<")):
        try:
            v = float(flt.get(k) or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            q += f" AND {MINS} {op} ?"
            args.append(v)
    try:
        days = int(flt.get("since") or 0)
    except (TypeError, ValueError):
        days = 0
    if days > 0:
        q += " AND added >= ?"
        args.append(int(time.time()) - days * 86400)
    if flt.get("hl"):
        q += " AND id IN (SELECT book_id FROM highlights WHERE deleted = 0)"
    if flt.get("fresh"):
        q += " AND COALESCE(progress, 0) < 1"
    return q


def list_docs(conn, settings, where, tab, kind=None, cat=None, limit=200, offset=0, sort="new", feed=None, flt=None):
    args, q = [], "SELECT * FROM docs WHERE where_ = ? AND status != 'deleted'"
    args.append(where)
    exp = expired_before(settings)
    if where == "feed":
        if tab == "seen":
            q += " AND (status = 'seen' OR added < ?)"
            args.append(exp)
        else:
            q += " AND status = 'unseen' AND added >= ?"
            args.append(exp)
        if cat:
            q += " AND category = ?"
            args.append(cat)
        if feed:
            q += " AND feed = ?"
            args.append(feed)
    elif kind == "starred":
        # The Shortlist, as in Readwise: starred (Karakeep's favourites), whatever the tab, until archived.
        q += " AND starred = 1 AND status NOT IN ('archive', 'deleted')"
    else:
        q += " AND status = ?"
        args.append(tab or "inbox")
        if kind:
            q += " AND kind = ?"
            args.append(kind)
    q += _filters(flt, args)
    q += " ORDER BY " + SORTS.get(sort, SORTS["new"])
    q += " LIMIT ? OFFSET ?"
    args += [limit, offset]
    hl = _hl_counts(conn)
    rows = [dict(r) for r in conn.execute(q, args)]
    for r in rows:
        r["highlights"] = hl.get(r["id"], 0)
        r["mins"] = round(r["duration"] / 60) if r.get("duration") else max(1, round((r["words"] or 0) / 238)) if r["words"] else None
        r["expired"] = where == "feed" and r["status"] == "unseen" and (r["added"] or 0) < exp
    return rows


def counts(conn, settings):
    exp = expired_before(settings)
    feed = conn.execute("SELECT category, COUNT(*) FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND added >= ? GROUP BY category",
                        (exp,)).fetchall()
    lib = conn.execute("SELECT kind, COUNT(*) FROM docs WHERE where_ = 'library' AND status = 'inbox' GROUP BY kind").fetchall()
    fc = json.loads((conn.execute("SELECT v FROM kv WHERE k = 'feed_counts'").fetchone() or ["{}"])[0])
    expired = conn.execute("SELECT COUNT(*) FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND added < ?", (exp,)).fetchone()[0]
    return {"feed": {r[0] or "": r[1] for r in feed}, "feed_total": sum(r[1] for r in feed),
            "freshrss_unread": fc.get("total"), "expired_in_daf": expired,
            "library": {r[0]: r[1] for r in lib},
            "emails_on": bool(settings.get("newsletters")),
            "starred": conn.execute("SELECT COUNT(*) FROM docs WHERE where_ = 'library' AND starred = 1 AND status NOT IN ('archive', 'deleted')").fetchone()[0]}


def feed_sources(conn, settings):
    """The Feed's folders and their feeds, each with what's unseen in it (Daf's window), for the
    source picker. FreshRSS's list is kept in kv, so the picker still works when it doesn't answer."""
    try:
        subs = freshrss.subscriptions()
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_subs', ?)", (json.dumps(subs),))
        for x in subs:      # items synced before Daf kept the feed's id: match them by its title
            conn.execute("UPDATE docs SET feed = ? WHERE where_ = 'feed' AND feed IS NULL AND source = ?", (x["id"], x["title"]))
        stale = False
    except Exception:  # noqa: BLE001
        subs = json.loads((conn.execute("SELECT v FROM kv WHERE k = 'feed_subs'").fetchone() or ["[]"])[0])
        stale = True
    exp = expired_before(settings)
    unseen = dict(conn.execute("SELECT feed, COUNT(*) FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND added >= ? "
                               "AND feed IS NOT NULL GROUP BY feed", (exp,)).fetchall())
    full, notify = set(settings.get("feed_full") or []), set(settings.get("feed_notify") or [])
    folders = {}
    for x in subs:
        f = folders.setdefault(x["folder"], {"name": x["folder"], "count": 0, "feeds": []})
        f["feeds"].append(dict(x, count=unseen.get(x["id"], 0), full=x["id"] in full, notify=x["id"] in notify))
        f["count"] += unseen.get(x["id"], 0)
    for f in folders.values():
        f["feeds"].sort(key=lambda x: x["title"].casefold())
    out = sorted(folders.values(), key=lambda f: (f["name"] == "", f["name"].casefold()))
    return {"folders": out, "total": sum(f["count"] for f in out), "stale": stale}


def feed_scope_ids(conn, settings, cat=None, feed=None, older=None):
    """The unseen items in a folder or a feed (or the whole Feed), older than `older` seconds if given."""
    q, args = "SELECT id, ext_id FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND added >= ?", [expired_before(settings)]
    if cat:
        q += " AND category = ?"
        args.append(cat)
    if feed:
        q += " AND feed = ?"
        args.append(feed)
    if older:
        q += " AND added < ?"
        args.append(int(time.time()) - int(older))
    return conn.execute(q, args).fetchall()


def mark_feed_seen(conn, settings, cat=None, feed=None, older=None):
    """Mark a folder or a feed seen, here and in FreshRSS. Returns the ids, for an undo."""
    rows = feed_scope_ids(conn, settings, cat, feed, older)
    freshrss.mark_read([r["ext_id"] for r in rows])
    conn.executemany("UPDATE docs SET status = 'seen' WHERE id = ?", [(r["id"],) for r in rows])
    return [r["id"] for r in rows]


def edit_feed(conn, stream, title=None, folder=None, full=None, notify=None):
    """Rename a feed or move it to another folder, in FreshRSS and on the items Daf has from it; and
    Daf's own two switches for it: always load the full article, notify of new posts."""
    subs = json.loads((conn.execute("SELECT v FROM kv WHERE k = 'feed_subs'").fetchone() or ["[]"])[0])
    old = next((x for x in subs if x["id"] == stream), None)
    if old is None:
        raise KeyError(stream)
    if full is not None or notify is not None:
        s = config.load_settings()
        for key, on in (("feed_full", full), ("feed_notify", notify)):
            if on is None:
                continue
            have = [f for f in s.get(key) or [] if f != stream]
            s[key] = have + [stream] if on else have
        config.save_settings(s)
        old["full"], old["notify"] = stream in (s.get("feed_full") or []), stream in (s.get("feed_notify") or [])
    title = " ".join(str(title or "").split())[:200] or None
    folder = None if folder is None else " ".join(str(folder).split())[:80]
    freshrss.edit_subscription(stream, title if title != old["title"] else None, folder, old["folder"])
    if title:
        conn.execute("UPDATE docs SET source = ? WHERE where_ = 'feed' AND feed = ?", (title, stream))
        old["title"] = title
    if folder is not None:
        conn.execute("UPDATE docs SET category = ? WHERE where_ = 'feed' AND feed = ?", (folder, stream))
        old["folder"] = folder
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_subs', ?)", (json.dumps(subs),))
    return old


def unfollow_feed(conn, stream):
    """Stop following a feed in FreshRSS. What's unseen from it leaves the Feed; highlighted items stay."""
    freshrss.unsubscribe(stream)
    conn.execute("UPDATE docs SET status = 'seen' WHERE where_ = 'feed' AND feed = ? AND status = 'unseen'", (stream,))
    subs = json.loads((conn.execute("SELECT v FROM kv WHERE k = 'feed_subs'").fetchone() or ["[]"])[0])
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES ('feed_subs', ?)", (json.dumps([x for x in subs if x["id"] != stream]),))


def get_doc(conn, doc_id, prefetch=False):
    """One doc with its text. A prefetch (the phone saving it for offline) doesn't mark it opened
    and doesn't start a PDF download."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        return None
    d = dict(d)
    row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    if row and row[0] not in ("[]", ""):
        blocks = json.loads(row[0])
    elif doc_id.startswith("kk:") and karakeep.mode() != "off":   # never read, or read before Karakeep had the page
        try:
            blocks = karakeep.fetch_content(conn, doc_id)
        except Exception as e:  # noqa: BLE001
            blocks, d["content_error"] = [], str(e)
    else:
        blocks = []
    if not blocks and d["where_"] == "library" and d["kind"] in ("article", "tweet") and d["url"] and not karakeep.writes() and not prefetch:
        # Daf keeps it: its page is being read (a new save), or is read now (one Karakeep never read)
        from . import media
        st = media.job_status(conn, "page", doc_id)
        if not st or st["status"] in ("queued", "running") or (st["status"] == "failed" and time.time() - (st.get("finished") or 0) > 3600):
            media.queue(conn, "page", doc_id)             # (a failed one is tried again after an hour)
            d["preparing"] = True
        elif st.get("error") and not d.get("content_error"):
            d["content_error"] = "Daf couldn't read the page: " + st["error"]
    if not blocks and d["kind"] == "pdf" and not prefetch:
        from . import media
        st = media.job_status(conn, "pdf", doc_id)
        if not st or st["status"] in ("queued", "running") or not st.get("error"):
            media.queue(conn, "pdf", doc_id)
            d["preparing"] = True
        else:
            d["content_error"] = st["error"]
    if d["kind"] == "video" and d["url"]:
        from . import social
        if social.is_reel(d["url"]):                 # a reel: Daf's own copy, its caption and transcript
            d["reel"] = True
            if social.media_path(doc_id).exists():
                from urllib.parse import quote
                d["media"] = "/api/media/" + quote(doc_id, safe="")
            if not blocks and not prefetch:
                from . import media
                st = media.job_status(conn, "reel", doc_id)
                if not st or (st["status"] == "failed" and st.get("error") != social.LOGIN_ERROR
                              and time.time() - (st.get("finished") or 0) > 3600):
                    media.queue(conn, "reel", doc_id)
                    d["preparing"] = True
                elif st["status"] in ("queued", "running"):
                    d["preparing"] = True
                elif st.get("error"):
                    d["content_error"] = st["error"]
    if d["kind"] == "podcast" and d.get("enclosure"):
        from . import episodes                       # its transcript in front of the show notes, and its player's details
        blocks = episodes.blocks(conn, d, blocks)
        d["episode"] = episodes.state(conn, d, opening=not prefetch)
        d["duration"] = d.get("duration") or d["episode"]["duration"]
    d["has_pdf"] = d["kind"] == "pdf"
    d["blocks"] = blocks
    d["mins"] = round(d["duration"] / 60) if d.get("duration") else max(1, round((d["words"] or 0) / 238)) if d["words"] else None
    d["counted"] = bool(config.load_settings()["count"].get(d["kind"] if d["kind"] in ("video", "podcast") else "article"))
    d["highlights"] = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.pos, h.created, h.color, h.source, "
        "CASE WHEN h.source = 'kindle' THEN COALESCE(s.user_note, h.note) ELSE s.user_note END AS user_note "
        "FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.book_id = ? AND h.deleted = 0 ORDER BY h.created", (doc_id,))]
    for h in d["highlights"]:
        try:
            h["pos"] = json.loads(h["pos"]) if h["pos"] else None
        except ValueError:
            h["pos"] = None
    d["asks"] = [dict(r) for r in conn.execute("SELECT q, quote, a, at FROM asks WHERE doc_id = ? ORDER BY at", (doc_id,))]
    from . import ink
    d["ink"] = ink.strokes(conn, doc_id)
    b = conn.execute("SELECT vault_path FROM books WHERE id = ?", (doc_id,)).fetchone()
    d["vault_path"] = b[0] if b else None
    d["vault_name"] = config.VAULT.name
    if not d["opened"] and not prefetch:
        conn.execute("UPDATE docs SET opened = ? WHERE id = ?", (int(time.time()), doc_id))
    return d


def set_status(conn, doc_id, status):
    """A document's place: unseen or seen in the Feed, inbox, later or archive in the Library, or
    deleted from either. Deleted is Daf's: a Feed item is marked read in FreshRSS, and a Karakeep
    one is deleted there only once Undo has had its time (purge_deleted), so Undo can bring it back."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    if d["status"] == "deleted" and d["deleted"] == 1 and status != "deleted" and doc_id.startswith("kk:") and karakeep.writes():
        raise ValueError("It's gone from Karakeep now; save it again")
    if d["where_"] == "feed":
        if status not in ("seen", "unseen", "deleted"):
            raise ValueError(status)
        read = status != "unseen"
        if read != (d["status"] != "unseen"):
            freshrss.mark_read([d["ext_id"]], read=read)
    else:
        if status not in ("inbox", "later", "archive", "deleted"):
            raise ValueError(status)
        if status != "deleted" and (status == "archive") != (d["status"] == "archive") and doc_id.startswith("kk:"):
            karakeep.set_archived(d["ext_id"], status == "archive")
    conn.execute("UPDATE docs SET status = ?, deleted = ? WHERE id = ?",
                 (status, int(time.time()) if status == "deleted" else None, doc_id))


UNDO_SECONDS = 600


def purge_deleted(conn):
    """Library documents deleted more than ten minutes ago leave Karakeep, and then Daf. One with
    highlights stays behind as a quiet row (deleted = 1), so its highlights keep their title.
    Anything else (an email, a Torah reading, a Feed item) keeps its row as deleted = 1 for good:
    the sync that brought it skips ids it already has, and a missing row would bring it back."""
    n, own = 0, not karakeep.writes()
    for r in conn.execute("SELECT id, ext_id FROM docs WHERE status = 'deleted' AND deleted > 1 AND deleted < ?",
                          (int(time.time()) - UNDO_SECONDS,)).fetchall():
        if own:
            # Daf keeps the Library: a quiet row stays, so Karakeep's read-only sync doesn't bring it back
            conn.execute("UPDATE docs SET deleted = 1 WHERE id = ?", (r["id"],))
            n += 1
            continue
        if r["id"].startswith("kk:") and r["ext_id"]:
            try:
                karakeep.delete(r["ext_id"])
            except karakeep.KarakeepError as e:
                if " 404 " not in str(e):
                    continue
        if not r["id"].startswith("kk:") or conn.execute("SELECT 1 FROM highlights WHERE book_id = ? AND deleted = 0 LIMIT 1", (r["id"],)).fetchone():
            conn.execute("UPDATE docs SET deleted = 1 WHERE id = ?", (r["id"],))
        else:
            conn.execute("DELETE FROM doc_content WHERE id = ?", (r["id"],))
            conn.execute("DELETE FROM docs WHERE id = ?", (r["id"],))
        n += 1
    return n


def set_starred(conn, doc_id, starred):
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    if d["where_"] != "library":
        raise ValueError("Save it to the Library first")
    if doc_id.startswith("kk:"):
        karakeep.set_favourited(d["ext_id"], starred)
    conn.execute("UPDATE docs SET starred = ? WHERE id = ?", (1 if starred else 0, doc_id))


def set_doc_tags(conn, doc_id, tags):
    """A document's tags. Karakeep items keep theirs in Karakeep (the next sync reads them back);
    feed items and emails keep them in Daf."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    clean = []
    for t in tags or []:
        t = " ".join(str(t).split()).strip().lstrip("#")[:60]
        if t and t.lower() not in {x.lower() for x in clean}:
            clean.append(t)
    old = json.loads(d["tags"]) if d["tags"] else []
    if doc_id.startswith("kk:") and d["ext_id"]:
        add = [t for t in clean if t not in old]
        gone = [t for t in old if t not in clean]
        if add:
            karakeep.attach_tags(d["ext_id"], add)
        if gone:
            karakeep.detach_tags(d["ext_id"], gone)
    conn.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(clean) if clean else None, doc_id))
    return clean


def all_doc_tags(conn):
    n = {}
    for (tags,) in conn.execute("SELECT tags FROM docs WHERE tags IS NOT NULL"):
        for t in json.loads(tags):
            n[t] = n.get(t, 0) + 1
    return sorted(n, key=lambda t: (-n[t], t.lower()))


def save_to_library(conn, doc_id):
    """Feed item → the Library (Daf's own, or Karakeep the old way). Highlights and ink move with it.
    Returns the new doc id."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d or not d["url"]:
        raise ValueError("Nothing to save")
    own = not karakeep.writes()
    if own:
        from . import pages
        had_doc = next((r for r in conn.execute("SELECT * FROM docs WHERE where_ = 'library' AND url IS NOT NULL AND instr(lower(url), ?) > 0",
                                                (pages.norm_url(d["url"]).split("://", 1)[-1].lower(),)).fetchall()
                        if pages.norm_url(r["url"]) == pages.norm_url(d["url"])), None)
        b = {"id": None}
        new_id = had_doc["id"] if had_doc else pages.make_id()
    else:
        b = karakeep.save(d["url"], d["title"])
        new_id = "kk:" + b["id"]
    blocks = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
    had = conn.execute("SELECT * FROM docs WHERE id = ?", (new_id,)).fetchone()
    if had:
        # Karakeep already had this link, so the Library already has its copy: that stays as it is
        # (its place, Later, note, star, tags, summary and text, maybe the whole page from behind a
        # paywall). The Feed item only adds: its highlights below, a longer text, a further place.
        conn.execute("UPDATE docs SET status = CASE WHEN status = 'deleted' THEN 'inbox' ELSE status END, deleted = NULL, "
                     "progress = MAX(COALESCE(progress, 0), ?), note = COALESCE(NULLIF(note, ''), ?), opened = COALESCE(opened, ?) WHERE id = ?",
                     (d["progress"] or 0, d["note"], d["opened"], new_id))
        mine = conn.execute("SELECT words FROM docs WHERE id = ?", (new_id,)).fetchone()[0] or 0
        if blocks and (d["words"] or 0) > mine and not conn.execute("SELECT 1 FROM doc_content WHERE id = ?", (new_id,)).fetchone():
            conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (new_id, blocks[0], int(time.time())))
    else:
        conn.execute(
            "INSERT INTO docs (id, kind, where_, status, title, author, source, category, url, published, added, words, summary, ext_id, progress, note, opened, "
            "enclosure, duration) VALUES (?, ?, 'library', 'inbox', ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id, d["kind"], d["title"], d["author"], d["source"], d["url"], d["published"], int(time.time()), d["words"],
             d["summary"], b["id"], d["progress"], d["note"], d["opened"], d["enclosure"], d["duration"]))   # an episode keeps its audio
        if blocks:
            conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)", (new_id, blocks[0], int(time.time())))
        if d["kind"] == "podcast":
            from . import episodes
            episodes.index(conn, new_id)           # its transcript too, for search
        if own:
            if d["thumb"]:
                conn.execute("UPDATE docs SET thumb = ? WHERE id = ?", (d["thumb"], new_id))
            from . import media
            if d["kind"] != "podcast":          # an episode's text is its show notes and transcript, not its web page
                media.queue(conn, "page", new_id)   # its picture kept, and the whole page when the feed gave a summary
    tags = json.loads(d["tags"]) if d["tags"] else []
    if tags and own:
        old = json.loads(had["tags"]) if had and had["tags"] else []
        conn.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(old + [t for t in tags if t not in old]), new_id))
    elif tags:                                  # tags given in Daf go along to Karakeep
        try:
            karakeep.attach_tags(b["id"], tags)
            old = json.loads(had["tags"]) if had and had["tags"] else []
            conn.execute("UPDATE docs SET tags = ? WHERE id = ?", (json.dumps(old + [t for t in tags if t not in old]), new_id))
        except Exception:  # noqa: BLE001 - saved is what matters
            pass
    conn.execute("UPDATE highlights SET book_id = ? WHERE book_id = ?", (new_id, doc_id))
    conn.execute("UPDATE ink SET doc = ? WHERE doc = ?", (new_id, doc_id))
    # Its note in the vault goes with it, unless the Library copy has one already.
    conn.execute("UPDATE books SET vault_path = (SELECT vault_path FROM books WHERE id = ?) WHERE id = ? AND vault_path IS NULL",
                 (doc_id, new_id))
    conn.execute("UPDATE OR IGNORE books SET id = ? WHERE id = ?", (new_id, doc_id))
    conn.execute("DELETE FROM books WHERE id = ?", (doc_id,))
    conn.execute("UPDATE OR IGNORE kv SET k = ? WHERE k = ?", ("vault_note:" + new_id, "vault_note:" + doc_id))
    conn.execute("UPDATE sessions SET item = ? WHERE item = ? AND source = 'article'", (new_id, doc_id))
    # Sent to the Kindle before it was saved: what comes back from the Kindle goes to the saved copy.
    conn.execute("UPDATE OR REPLACE kindle_sent SET doc_id = ? WHERE doc_id = ?", (new_id, doc_id))
    conn.execute("UPDATE kindle_epubs SET parts = replace(parts, json_quote(?), json_quote(?)) WHERE instr(parts, json_quote(?)) > 0",
                 (doc_id, new_id, doc_id))
    try:
        freshrss.mark_read([d["ext_id"]])
    except Exception:  # noqa: BLE001 - saved is what matters
        pass
    conn.execute("UPDATE docs SET status = 'seen' WHERE id = ?", (doc_id,))
    try:                                        # the note now points at the Library copy, with its text
        vaultnotes.write_for(conn, config.load_settings(), new_id)
    except Exception:  # noqa: BLE001 - saved is what matters
        log.exception("vault note after saving %s", new_id)
    return new_id


def _ensure_book(conn, d):
    from . import library
    private = 1 if library.is_private(f"{d['title']} {d['source'] or ''} {d['category'] or ''}", config.load_settings()) else 0
    conn.execute(
        "INSERT INTO books (id, kind, title, author, url, private) VALUES (?, 'article', ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET title = excluded.title, url = excluded.url, private = excluded.private",
        (d["id"], d["title"], d["author"] or d["source"], d["url"], private))


COLORS = ("yellow", "green", "blue", "pink", "purple")


def edit_meta(conn, doc_id, title=None, author=None):
    """Your own title and author for a document. Karakeep and FreshRSS keep theirs; Daf
    lays this one over them after every sync (apply_edits)."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    title = (title or "").strip()[:300] or None
    author = (author or "").strip()[:200] or None
    conn.execute("INSERT INTO doc_edits (id, title, author, updated) VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                 "title = excluded.title, author = excluded.author, updated = excluded.updated", (doc_id, title, author, int(time.time())))
    apply_edits(conn, doc_id)


def apply_edits(conn, doc_id=None):
    rows = conn.execute("SELECT id, title, author FROM doc_edits" + (" WHERE id = ?" if doc_id else ""), (doc_id,) if doc_id else ()).fetchall()
    for r in rows:
        if r["title"]:
            conn.execute("UPDATE docs SET title = ? WHERE id = ?", (r["title"], r["id"]))
            conn.execute("UPDATE books SET title = ? WHERE id = ?", (r["title"], r["id"]))
        if r["author"]:
            conn.execute("UPDATE docs SET author = ? WHERE id = ?", (r["author"], r["id"]))
            conn.execute("UPDATE books SET author = ? WHERE id = ?", (r["author"], r["id"]))
    return len(rows)


def _pdf_pos(pdf):
    """A PDF page highlight's place: {"pg": page (1-based), "r": [[x, y, w, h], …] as fractions of the page}."""
    if not isinstance(pdf, dict):
        return None
    try:
        pg = int(pdf.get("pg"))
        rects = [[round(float(v), 5) for v in r[:4]] for r in (pdf.get("r") or [])[:80] if isinstance(r, (list, tuple)) and len(r) >= 4]
    except (TypeError, ValueError):
        return None
    return {"pg": pg, "r": rects} if pg >= 1 and rects else None


IMG_MD = re.compile(r"^!\[([^\]\n]*)\]\((\S+)\)$")


def picture_text(src, alt=""):
    """A highlighted picture is kept as Markdown's picture, which the vault shows and Daf draws."""
    alt = re.sub(r"[\[\]\n]+", " ", alt or "").strip()[:200]
    return f"![{alt}]({src.replace(' ', '%20').replace(')', '%29')})"


def plain(text):
    """A highlight's words for a screen that shows only words (the Kindle, Signal): a picture is said."""
    m = IMG_MD.match((text or "").strip())
    return (f"[A picture: {m.group(1).strip()}]" if m.group(1).strip() else "[A picture]") if m else text


def add_highlight(conn, settings, doc_id, block, start, end, text, note=None, t=None, color=None, end_block=None, replaces=None, pdf=None, created=None, img=None):
    """img: the picture's address, for a highlighted picture (text is then its Markdown)."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    _ensure_book(conn, d)
    if img:
        if not re.match(r"^https?://\S+$", img) or len(img) > 2000:
            raise ValueError("A picture on the web")
        m = IMG_MD.match((text or "").strip())
        text = picture_text(img, m.group(1) if m else "")
    text = (text or "").strip()
    hid = "d" + hashlib.sha1(f"{doc_id}|{block}|{start}|{text}".encode()).hexdigest()[:16]
    conn.execute("INSERT OR REPLACE INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted, color) "
                 "VALUES (?, ?, 'daf', ?, NULL, NULL, NULL, ?, ?, ?, 0, ?)",
                 (hid, doc_id, text, int(created or time.time()), json.dumps({"b": block, "s": start, "e": end, **({"t": t} if t is not None else {}),
                                                                   **({"be": end_block} if end_block is not None and end_block != block else {}),
                                                                   **({"pdf": _pdf_pos(pdf)} if _pdf_pos(pdf) else {}),
                                                                   **({"img": img} if img else {})}),
                  int(time.time()), color if color in COLORS else None))
    from . import review
    review.carry(conn, hid, replaces, own=("daf",))
    if note:
        review.set_note(conn, hid, note)
    vaultnotes.write_article(conn, settings, doc_id)
    return hid


def remove_highlight(conn, settings, hl_id):
    h = conn.execute("SELECT book_id, source FROM highlights WHERE id = ?", (hl_id,)).fetchone()
    if not h or h["source"] not in ("daf", "epub", "paper"):
        raise ValueError("Only highlights made in Daf can be removed here")
    conn.execute("UPDATE highlights SET deleted = 1 WHERE id = ?", (hl_id,))
    vaultnotes.write_for(conn, settings, h["book_id"])


def restore_highlight(conn, settings, hl_id):
    """Undo a removal."""
    h = conn.execute("SELECT book_id, source FROM highlights WHERE id = ?", (hl_id,)).fetchone()
    if not h:
        raise ValueError("No such highlight")
    conn.execute("UPDATE highlights SET deleted = 0 WHERE id = ?", (hl_id,))
    vaultnotes.write_for(conn, settings, h["book_id"])


def set_progress(conn, doc_id, pct):
    conn.execute("UPDATE docs SET progress = MAX(progress, ?) WHERE id = ?", (max(0.0, min(100.0, float(pct))), doc_id))


def set_note(conn, settings, doc_id, note):
    conn.execute("UPDATE docs SET note = ? WHERE id = ?", ((note or "").strip() or None, doc_id))
    if conn.execute("SELECT 1 FROM highlights WHERE book_id = ? AND deleted = 0", (doc_id,)).fetchone() or note:
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
        _ensure_book(conn, d)
        vaultnotes.write_article(conn, settings, doc_id)


# ---- reading time -------------------------------------------------------------

def beat(conn, settings, doc_id, seconds, at=None):
    """The reader reports active reading in short beats. One session per article per day.
    Beats made offline arrive later with `at`, the time they happened (within a week)."""
    seconds = max(0, min(90, int(seconds)))
    if not seconds:
        return
    d = conn.execute("SELECT title, source, kind FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d or d["kind"] == "podcast":            # an episode's time is its listening (gpodder.py), which never counts
        return
    src = "video" if d["kind"] == "video" else "article"
    now = int(time.time())
    try:
        at = int(at) if at is not None else None
    except (TypeError, ValueError):
        at = None
    if at is None or not (now - 7 * 86400 <= at <= now + 60):
        at = now
    day = datetime.fromtimestamp(at, T.tz_of(settings)).date().isoformat()
    sid = f"art:{doc_id}:{day}"
    # One statement, so two first beats at once can't both try to make the session.
    conn.execute("INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private, note) "
                 "VALUES (?, ?, 'daf-read', ?, ?, ?, ?, ?, NULL, 0, NULL) "
                 "ON CONFLICT(id) DO UPDATE SET seconds = seconds + excluded.seconds",
                 (sid, src, doc_id, d["title"], d["source"], T.beat_start(at, seconds, settings), seconds))


# ---- Ask ----------------------------------------------------------------------

def ask(conn, doc_id, question, quote=None):
    d = get_doc(conn, doc_id)
    if not d:
        raise KeyError(doc_id)
    text = "\n\n".join(b["x"] for b in d["blocks"] if b.get("t") != "img")
    words = text.split()
    if len(words) > 14000:
        text = " ".join(words[:14000]) + " […]"
    hls = "\n".join(f"- {h['text']}" + (f" (the reader's note: {h['user_note']})" if h.get("user_note") else "") for h in d["highlights"])
    from . import ai
    prompt = (
        "You are the Ask feature in Daf, a personal reading app. " + ai.prompt("ask") + "\n\n"
        f"Document: {d['title']} ({d['source'] or d['url'] or ''})\n\n<document>\n{text}\n</document>\n\n"
        + (f"The reader's highlights in it:\n{hls}\n\n" if hls else "")
        + (f"The passage the reader selected:\n\"{quote}\"\n\n" if quote else "")
        + f"The reader's question: {question}"
    )
    try:
        answer = ai.run(prompt)
    except RuntimeError as e:
        answer = str(e) or "No answer came back."
    conn.execute("INSERT INTO asks (doc_id, q, quote, a, at) VALUES (?, ?, ?, ?, ?)", (doc_id, question, quote, answer, int(time.time())))
    return answer


def summarize(conn, doc_id):
    """Two or three sentences on what a document says, by Claude, the way Readwise's Ghostreader
    sums up what you save. Kept in docs.ai_summary."""
    d = get_doc(conn, doc_id, prefetch=True)
    if not d or not d["blocks"]:
        return None
    text = "\n\n".join(b["x"] for b in d["blocks"] if b.get("t") not in ("img", "pg") and (b.get("x") or "").strip())
    words = text.split()
    if len(words) < 60:
        return None
    if len(words) > 9000:
        text = " ".join(words[:9000]) + " […]"
    from . import ai
    prompt = (ai.prompt("summary") + "\n\n"
              f"Title: {d['title']}\nSource: {d['source'] or d['url'] or ''}\n\n<document>\n{text}\n</document>")
    out = ai.run(prompt)
    out = re.sub(r"\s+", " ", out)[:900]
    conn.execute("UPDATE docs SET ai_summary = ? WHERE id = ?", (out, doc_id))
    return out


def queue_summaries(conn, settings, limit=6):
    """Library documents with text and no summary yet, a few per sync, unless Preferences → AI says
    no. Private ones never go to the model."""
    from . import ai, library, media
    if not ai.settings(settings)["auto_summary"]:
        return 0
    n = 0
    # Too short to summarize (summarize() wants 60 words) is skipped here, and so is one that already
    # has a job, whatever came of it: otherwise the newest short items (tweets) would be queued
    # again every sync and the older articles would never get their turn. pages.keep_text drops the
    # job when a longer text arrives, so that one is summarized again.
    for r in conn.execute("SELECT d.id, d.title, d.source, d.category FROM docs d JOIN doc_content c ON c.id = d.id "
                          "WHERE d.where_ = 'library' AND d.status NOT IN ('archive', 'deleted') AND d.ai_summary IS NULL "
                          "AND COALESCE(d.words, 60) >= 60 AND d.id NOT IN (SELECT ref FROM jobs WHERE kind = 'summary') "
                          "ORDER BY d.added DESC").fetchall():
        if n >= limit:
            break
        if library.is_private(f"{r['title']} {r['source'] or ''} {r['category'] or ''}", settings):
            continue
        media.queue(conn, "summary", r["id"])
        n += 1
    return n


# ---- read-aloud ----------------------------------------------------------------

def _kokoro():
    ip = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", "kokoro-tts"],
                        capture_output=True, text=True, timeout=10).stdout.strip()
    if not ip:
        raise RuntimeError("Kokoro isn't running")
    return f"http://{ip}:8880"


def tts(text, voice, speed=1.0):
    """MP3 for one paragraph, cached on disk by text and voice."""
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{speed}|{text}".encode()).hexdigest()
    path = TTS_DIR / f"{key}.mp3"
    if not path.exists():
        body = json.dumps({"model": "kokoro", "input": text[:4000], "voice": voice, "response_format": "mp3", "speed": speed}).encode()
        req = urllib.request.Request(_kokoro() + "/v1/audio/speech", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    return path


def voices():
    try:
        with urllib.request.urlopen(_kokoro() + "/v1/audio/voices", timeout=10) as r:
            return json.loads(r.read()).get("voices", [])
    except Exception:  # noqa: BLE001
        return []


def prune_tts(max_mb=300):
    files = sorted(TTS_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime) if TTS_DIR.exists() else []
    total = sum(p.stat().st_size for p in files)
    while files and total > max_mb * 1024 * 1024:
        p = files.pop(0)
        total -= p.stat().st_size
        p.unlink(missing_ok=True)


def push_inbox(conn):
    """Links shared from the phone go to the Library (Daf's own, or Karakeep the old way)."""
    for r in conn.execute("SELECT * FROM inbox WHERE status = 'new' AND url != '' ORDER BY id").fetchall():
        try:
            if karakeep.writes():
                karakeep.save(r["url"], r["title"] or None)
            else:
                from . import pages
                pages.save_page(conn, r["url"], r["title"] or None)
            conn.execute("UPDATE inbox SET status = 'saved' WHERE id = ?", (r["id"],))
        except Exception:  # noqa: BLE001
            conn.execute("UPDATE inbox SET status = 'failed' WHERE id = ?", (r["id"],))


def expire_in_freshrss(conn, settings):
    """Mark everything older than the expiry window read in FreshRSS too (only when you ask)."""
    before = expired_before(settings)
    n = conn.execute("SELECT v FROM kv WHERE k = 'feed_counts'").fetchone()
    freshrss.mark_all_read_before(before)
    conn.execute("UPDATE docs SET status = 'seen' WHERE where_ = 'feed' AND status = 'unseen' AND added < ?", (before,))
    return json.loads(n[0]).get("total") if n else None
