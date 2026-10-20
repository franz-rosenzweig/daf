"""The Library home: shelves of cards, as on Readwise Reader's Home.

Continue reading (books and articles in progress), Recently added, Quick reads, Long reads,
Recently highlighted, New in the Feed. Each card links to where it opens: books in Daf's
book reader when Calibre has a file, articles and videos in the reading view.
"""
import time

from . import ebooks, reader


def _mins(r):
    if r.get("duration"):
        return round(r["duration"] / 60)
    return max(1, round((r["words"] or 0) / 238)) if r.get("words") else None


def _doc_card(r):
    return {"type": "doc", "id": r["id"], "kind": r["kind"], "title": r["title"], "author": r["author"], "source": r["source"],
            "thumb": r["thumb"], "mins": _mins(r), "progress": r["progress"] or 0, "href": "#read/" + r["id"]}


def _book_card(b, readable, daf_pos):
    pos = daf_pos.get(b["id"])
    progress = round(pos * 100, 1) if pos is not None else (b["progress"] or 0)
    return {"type": "book", "id": b["id"], "kind": "book", "title": b["title"], "author": b["author"], "source": "Book",
            "has_cover": bool(b["calibre_path"]), "mins": None, "progress": progress,
            "href": ("#ebook/" if b["id"] in readable else "#book/") + b["id"], "note": b["progress_note"]}


def shelves(conn, settings):
    now = int(time.time())
    readable = ebooks.readable_ids(conn)
    daf_pos = {r[0]: r[1] for r in conn.execute("SELECT book_id, fraction FROM book_positions")}
    out = {}

    books = [_book_card(b, readable, daf_pos) for b in conn.execute(
        "SELECT * FROM books WHERE kind = 'book' AND private = 0 AND last_read > ? ORDER BY last_read DESC LIMIT 30", (now - 60 * 86400,))]
    books = [b for b in books if 2 <= (b["progress"] or 0) <= 97][:10]
    docs = [_doc_card(dict(r)) for r in conn.execute(
        "SELECT * FROM docs WHERE where_ = 'library' AND status NOT IN ('archive', 'deleted') AND progress BETWEEN 3 AND 95 ORDER BY COALESCE(opened, added) DESC LIMIT 8")]
    out["continue"] = books + docs

    lib = [dict(r) for r in conn.execute("SELECT * FROM docs WHERE where_ = 'library' AND status IN ('inbox', 'later') ORDER BY added DESC LIMIT 300")]
    out["recent"] = [_doc_card(r) for r in lib if (r["added"] or 0) > now - 7 * 86400][:12]
    out["quick"] = [_doc_card(r) for r in lib if _mins(r) and _mins(r) <= 10][:12]
    out["long"] = [_doc_card(r) for r in lib if _mins(r) and _mins(r) >= 30][:12]

    hl = []
    for r in conn.execute(
            "SELECT h.book_id, MAX(h.created) AS at, COUNT(*) AS n FROM highlights h JOIN books b ON b.id = h.book_id "
            "WHERE h.deleted = 0 AND b.private = 0 AND h.created > ? GROUP BY h.book_id ORDER BY at DESC LIMIT 12", (now - 21 * 86400,)):
        d = conn.execute("SELECT * FROM docs WHERE id = ?", (r["book_id"],)).fetchone()
        if d and d["status"] == "deleted":
            continue
        if d:
            card = _doc_card(dict(d))
        else:
            b = conn.execute("SELECT * FROM books WHERE id = ?", (r["book_id"],)).fetchone()
            if not b or b["kind"] != "book":
                continue
            card = _book_card(b, readable, daf_pos)
        card["highlights"] = r["n"]
        hl.append(card)
    out["highlighted"] = hl

    exp = reader.expired_before(settings)
    out["feed"] = [_doc_card(dict(r)) for r in conn.execute(
        "SELECT * FROM docs WHERE where_ = 'feed' AND status = 'unseen' AND added >= ? ORDER BY added DESC LIMIT 12", (exp,))]
    return out
