"""Every highlight, in one index.

- Kindle: KOReader's sidecars (synced to morten by Syncthing), the freshest and
  fullest record, with KoInsight's annotation table filling any book whose
  sidecar never synced.
- Karakeep: highlights on saved articles, read-only from its SQLite file.
- Audiobookshelf: bookmarks (a time and a title, no text yet; Phase 5
  transcribes them), kept apart from highlights.

A highlight's id is stable across syncs and Kindle copies: a hash of its book and
its normalized text. Review state and Daf notes hang off that id.
"""
import hashlib
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .. import config, library
from ..db import read_only


def _norm_text(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def _hid(prefix, book_id, text):
    return prefix + hashlib.sha1(f"{book_id}|{_norm_text(text)}".encode()).hexdigest()[:16]


def _epoch(local, tz):
    try:
        return int(datetime.strptime(local[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz).timestamp())
    except (TypeError, ValueError):
        return None


class DafEpubHighlights:
    """Kindle highlights made in an EPUB from Send to Kindle, as highlights on the articles: placed
    in each article's text (so they open at their spot in Daf), with the EPUB's md5 kept as `k`."""

    def __init__(self, conn, epubs):
        self.conn, self.epubs, self.docs, self.blocks = conn, epubs, set(), {}
        ids = list({d for parts in epubs.values() for d, _ in parts})
        self.titles = {}
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            self.titles.update(conn.execute(f"SELECT id, title FROM docs WHERE id IN ({','.join('?' * len(chunk))})", chunk).fetchall())

    def _blocks(self, doc):
        if doc not in self.blocks:
            r = self.conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc,)).fetchone()
            try:
                self.blocks[doc] = json.loads(r[0]) if r and r[0] else []
            except ValueError:
                self.blocks[doc] = []
        return self.blocks[doc]

    def row(self, md5, a, text, note, created):
        from .. import kindlesend
        doc = kindlesend.doc_for(self.epubs[md5], a, self.titles)
        if not doc or doc not in self.titles:
            return None
        self.docs.add(doc)
        pos = (kindlesend.place(self._blocks(doc), text) if text else None) or {}
        return {"id": _hid("k", doc, text or note), "book_id": doc, "source": "kindle", "text": text or None, "note": note,
                "chapter": None, "page": None, "created": created, "pos": json.dumps({**pos, "k": md5})}

    def finish(self):
        """Each article with a Kindle highlight is in the Highlights page and gets its vault note."""
        from .. import reader
        for doc in self.docs:
            d = self.conn.execute("SELECT * FROM docs WHERE id = ?", (doc,)).fetchone()
            if d:
                reader._ensure_book(self.conn, d)


def import_all(conn, settings):
    now = int(time.time())
    tz = ZoneInfo(settings.get("home_tz") or "America/Phoenix")
    rows = {}
    # Articles sent with Send to Kindle: a highlight there belongs to the article it was made in.
    from .. import kindlesend
    daf_epubs = kindlesend.epubs(conn)
    on_docs, seen_epubs = DafEpubHighlights(conn, daf_epubs), set()

    # Kindle sidecars.
    for path, t in library.sidecars(conn):
        md5 = t.get("partial_md5_checksum")
        dp = t.get("doc_props") or {}
        bid = library.book_for_md5(conn, md5) if md5 else None
        if not bid and dp.get("title"):
            bid = f"md5:{md5}" if md5 else None
        anns = t.get("annotations") or []
        if isinstance(anns, dict):
            anns = list(anns.values())
        if md5 in daf_epubs:
            seen_epubs.add(md5)
        for a in anns:
            if not isinstance(a, dict):
                continue
            text = (a.get("text") or "").strip()
            note = (a.get("note") or "").strip() or None
            if not text and not note:
                continue
            if not a.get("pos0") and text.startswith("in ") and len(text) < 60 and not note:
                continue          # a bare bookmark, not a highlight
            created = _epoch(a.get("datetime"), tz)
            if md5 in daf_epubs:
                r = on_docs.row(md5, a, text, note, created)
                if r and (r["id"] not in rows or (rows[r["id"]]["created"] or 0) < (created or 0)):
                    rows[r["id"]] = r
                continue
            hid = _hid("k", bid, text or note)
            prev = rows.get(hid)
            if prev and (prev["created"] or 0) >= (created or 0):
                continue
            pos = a.get("pos0")
            rows[hid] = {"id": hid, "book_id": bid, "source": "kindle", "text": text or None, "note": note,
                         "chapter": a.get("chapter") if isinstance(a.get("chapter"), str) else None,
                         "page": a.get("pageno") if isinstance(a.get("pageno"), int) else None, "created": created,
                         "pos": pos if isinstance(pos, str) or pos is None else json.dumps(pos)}   # PDFs give a table

    # KoInsight fills books whose sidecar never reached morten.
    try:
        k = read_only(config.KOINSIGHT_DB)
        try:
            for md5, text, note, chapter, pageno, dt, deleted in k.execute(
                    "SELECT book_md5, text, note, chapter, pageno, datetime, deleted_at FROM annotation"):
                if deleted or not (text or note):
                    continue
                if md5 in daf_epubs:
                    r = on_docs.row(md5, {"chapter": chapter}, (text or "").strip(), (note or "").strip() or None, _epoch(dt, tz))
                    if r and r["id"] not in rows:
                        rows[r["id"]] = r
                    continue
                bid = library.book_for_md5(conn, md5) or f"md5:{md5}"
                hid = _hid("k", bid, text or note)
                if hid in rows:
                    continue
                rows[hid] = {"id": hid, "book_id": bid, "source": "kindle", "text": (text or "").strip() or None,
                             "note": (note or "").strip() or None, "chapter": chapter, "page": pageno,
                             "created": _epoch(dt, tz), "pos": None}
        finally:
            k.close()
    except Exception:  # noqa: BLE001 - KoInsight is a fallback
        pass

    # Karakeep: articles become books of kind 'article'.
    try:
        kk = read_only(config.KARAKEEP_DB)
        try:
            for hid, bm, text, note, created, title, url, publisher in kk.execute(
                    "SELECT h.id, h.bookmarkId, h.text, h.note, h.createdAt, COALESCE(b.title, l.title), l.url, l.publisher "
                    "FROM highlights h JOIN bookmarks b ON b.id = h.bookmarkId LEFT JOIN bookmarkLinks l ON l.id = b.id"):
                bid = f"kk:{bm}"
                conn.execute(
                    "INSERT INTO books (id, kind, title, author, url, private) VALUES (?, 'article', ?, ?, ?, 0) "
                    "ON CONFLICT(id) DO UPDATE SET title = excluded.title, author = excluded.author, url = excluded.url",
                    (bid, re.sub(r"\s+[|·-]\s+[^|·-]+$", "", title or url or "Saved article"), publisher, url))
                conn.execute("INSERT OR REPLACE INTO book_keys (key, book_id) VALUES (?, ?)", (bid, bid))
                rows["kk" + hid] = {"id": "kk" + hid, "book_id": bid, "source": "karakeep", "text": text, "note": note,
                                    "chapter": None, "page": None,
                                    "created": int(created / 1000) if created and created > 1e11 else created, "pos": None}
        finally:
            kk.close()
    except Exception:  # noqa: BLE001
        pass

    # Readwise, the years before Daf: its exports in the vault's clippings.
    rw_ok, rw_tags = False, {}
    try:
        from . import readwise
        for r in readwise.rows(conn, settings, tz):
            rw_tags[r["id"]] = r.pop("tags")
            rows[r["id"]] = r
        rw_ok = (config.VAULT / readwise.FOLDER).is_dir()
    except Exception:  # noqa: BLE001 - the vault is a source like any other
        pass
    if rw_tags:                                   # Readwise's tags, once: one taken off in Daf stays off
        known = {r[0] for r in conn.execute("SELECT id FROM highlights WHERE source = 'readwise'")}
        from .. import review as _review
        for hid, tags in rw_tags.items():
            if hid not in known and tags:
                _review.add_tags(conn, hid, tags)

    # A highlight made in Daf and then added to the Kindle by the Daf plugin comes back in the
    # sidecar; it's the same highlight, so the Daf one stands and the Kindle copy is skipped.
    def _same(t):
        return re.sub(r"[\W_]+", " ", (t or "").lower()).strip()
    made_in_daf = {(r[0], _same(r[1])) for r in conn.execute("SELECT book_id, text FROM highlights WHERE source = 'epub' AND deleted = 0")}
    rows = {k: v for k, v in rows.items() if not (v["source"] == "kindle" and (v["book_id"], _same(v["text"])) in made_in_daf)}

    # A note typed on the Kindle with ".tag" in it tags the highlight, as in Readwise. Only for a note
    # that's new or changed, so a tag taken off in Daf stays off.
    from .. import review
    old_notes = {r[0]: r[1] for r in conn.execute("SELECT id, note FROM highlights WHERE source IN ('kindle', 'karakeep', 'readwise')")}
    for r in rows.values():
        if r.get("note") and old_notes.get(r["id"]) != r["note"] and review.DOT_TAG.search(r["note"]):
            review.add_tags(conn, r["id"], review.dot_tags(r["note"]))

    cols = ["id", "book_id", "source", "text", "note", "chapter", "page", "created", "pos"]
    conn.executemany(
        f"INSERT INTO highlights ({', '.join(cols)}, seen, deleted) VALUES ({', '.join('?' * len(cols))}, ?, 0) "
        "ON CONFLICT(id) DO UPDATE SET book_id = excluded.book_id, text = excluded.text, note = excluded.note, "
        "chapter = excluded.chapter, page = excluded.page, created = excluded.created, pos = excluded.pos, "
        "seen = excluded.seen, deleted = 0",
        [tuple(r[c] for c in cols) + (now,) for r in rows.values()])
    # Gone from every source: deleted on the Kindle. Daf notes on it are kept. A digest deleted from
    # the Kindle takes its sidecar with it, but not its highlights: those stay with their articles.
    gone = "('kindle', 'karakeep', 'readwise')" if rw_ok else "('kindle', 'karakeep')"   # no vault, no verdict on Readwise's
    conn.execute(f"UPDATE highlights SET deleted = 1 WHERE seen < ? AND source IN {gone} AND NOT "
                 "(json_valid(pos) AND json_extract(pos, '$.k') IS NOT NULL AND json_extract(pos, '$.k') NOT IN "
                 f"({','.join('?' * len(seen_epubs))}))", (now, *seen_epubs))
    on_docs.finish()

    # Audiobookshelf bookmarks.
    try:
        a = read_only(config.ABS_DB)
        try:
            row = a.execute("SELECT bookmarks FROM users WHERE username = ?", (config.ABS_USER,)).fetchone()
        finally:
            a.close()
        # Upsert, so the "transcribed" mark survives; drop bookmarks deleted in Audiobookshelf.
        present = []
        for bm in json.loads(row[0] or "[]") if row else []:
            bid = conn.execute("SELECT book_id FROM book_keys WHERE key = ?", (f"abs:{bm.get('libraryItemId')}",)).fetchone()
            bid = bid[0] if bid else None
            title = (bm.get("title") or "").strip()
            created = int((bm.get("createdAt") or 0) / 1000)
            bmid = f"{bm.get('libraryItemId')}:{bm.get('time')}"
            present.append(bmid)
            conn.execute("INSERT INTO audio_bookmarks (id, book_id, title, at, created) VALUES (?, ?, ?, ?, ?) "
                         "ON CONFLICT(id) DO UPDATE SET book_id = excluded.book_id, title = excluded.title, at = excluded.at",
                         (bmid, bid, title, bm.get("time"), created))
            # A bookmark whose title is a sentence is a quote typed while listening: a highlight.
            if bid and len(title) >= 25 and " " in title:
                hid = _hid("a", bid, title)
                conn.execute(
                    "INSERT INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted) "
                    "VALUES (?, ?, 'audiobookshelf', ?, NULL, NULL, NULL, ?, ?, ?, 0) "
                    "ON CONFLICT(id) DO UPDATE SET seen = excluded.seen, deleted = 0, pos = excluded.pos",
                    (hid, bid, title, created, json.dumps({"t": bm.get("time")}), now))
        if row is not None:
            if present:
                conn.execute(f"DELETE FROM audio_bookmarks WHERE id NOT IN ({','.join('?' * len(present))})", present)
            else:
                conn.execute("DELETE FROM audio_bookmarks")
    except Exception:  # noqa: BLE001
        pass
    return len(rows)
