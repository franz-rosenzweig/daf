"""The daily review: a few highlights a day, spaced so kept ones come back less often.

Each local day gets one fixed set (stored in review_days), so the morning message,
the web app and the Kindle all show the same five. Selection:

1. highlights that are due (kept before, due date reached), oldest due first, at most 3;
2. then highlights never reviewed, favouring the nightstand and recent highlights;
3. no more than 2 from one book; nothing private, deleted or too short.

Keep:  first time 4 days, then the interval grows 2.5x (cap one year).
Less:  pushed out at least 120 days and the interval quadruples.
Note:  saves the note (written to the vault) and counts as a keep.
"""
import json
import re
import random
import time
from datetime import date, timedelta

from . import library, today as T

MIN_LEN = 30


def _candidates(conn):
    return [dict(r) for r in conn.execute(
        "SELECT h.*, b.title AS book_title, b.author AS book_author, b.kind AS book_kind, b.private AS private, "
        "s.status AS r_status, s.due AS r_due, s.interval AS r_interval, s.reviews AS r_reviews, s.user_note AS user_note, s.tags AS r_tags, s.fav AS r_fav "
        "FROM highlights h LEFT JOIN books b ON b.id = h.book_id LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.deleted = 0 AND h.text IS NOT NULL AND length(h.text) >= ? AND COALESCE(b.private, 0) = 0",
        (MIN_LEN,))]


def build_day(conn, settings, day=None):
    day = day or T.today(settings)
    key = day.isoformat()
    row = conn.execute("SELECT ids FROM review_days WHERE day = ?", (key,)).fetchone()
    if row:
        return json.loads(row["ids"])
    size = settings.get("review_size", 5)
    freq = {b: f for b, f in conn.execute("SELECT book_id, freq FROM book_review")}
    # A day built ahead (the apps keep the next days for offline) doesn't repeat the days before it.
    taken = set()
    for (ids,) in conn.execute("SELECT ids FROM review_days WHERE day >= ? AND day < ?", (T.today(settings).isoformat(), key)):
        taken.update(json.loads(ids))
    cands = [c for c in _candidates(conn) if freq.get(c["book_id"]) != "never" and c["id"] not in taken]
    night = {b["id"] for b in library.nightstand(conn, settings)}
    due = sorted([c for c in cands if c["r_due"] and c["r_due"] <= key], key=lambda c: c["r_due"])
    fresh = [c for c in cands if c["r_status"] in (None, "noted")]   # "noted": a note added outside review
    rng = random.Random(key)
    now = time.time()

    def weight(c):
        w = 1.0
        if c["book_id"] in night:
            w *= 3
        if c["created"] and now - c["created"] < 60 * 86400:
            w *= 2
        if c["note"]:
            w *= 1.5
        if c.get("r_fav"):
            w *= 2
        f = freq.get(c["book_id"])
        if f == "more":
            w *= 2.5
        elif f == "less":
            w *= 0.35
        return w

    picked, per_book = [], {}

    def take(c):
        if len(picked) >= size or per_book.get(c["book_id"], 0) >= 2 or c["id"] in picked:
            return
        picked.append(c["id"])
        per_book[c["book_id"]] = per_book.get(c["book_id"], 0) + 1

    for c in [c for c in due if freq.get(c["book_id"]) != "less"][:3]:
        take(c)
    pool = fresh[:]
    while pool and len(picked) < size:
        c = rng.choices(pool, weights=[weight(x) for x in pool])[0]
        pool.remove(c)
        take(c)
    for c in due[3:]:
        take(c)
    conn.execute("INSERT OR REPLACE INTO review_days (day, ids, done) VALUES (?, ?, '{}')", (key, json.dumps(picked)))
    return picked


def review_streak(conn, settings):
    """Days in a row with the daily review finished, and the last seven days (oldest first)."""
    today = T.today(settings)
    finished = {}
    for r in conn.execute("SELECT day, ids, done FROM review_days WHERE day >= ?", ((today - timedelta(days=400)).isoformat(),)):
        ids, done = json.loads(r["ids"]), json.loads(r["done"] or "{}")
        finished[r["day"]] = bool(ids) and all(i in done for i in ids)
    d, n = today, 0
    if not finished.get(d.isoformat()):
        d -= timedelta(days=1)
    while finished.get(d.isoformat()):
        n += 1
        d -= timedelta(days=1)
    week = [{"date": (today - timedelta(days=6 - k)).isoformat(), "done": finished.get((today - timedelta(days=6 - k)).isoformat(), False)} for k in range(7)]
    return {"days": n, "week": week}


def day_items(conn, settings, day=None):
    day = day or T.today(settings)
    ids = build_day(conn, settings, day)
    done = json.loads((conn.execute("SELECT done FROM review_days WHERE day = ?", (day.isoformat(),)).fetchone() or {"done": "{}"})["done"])
    by_id = {c["id"]: c for c in _candidates(conn)}
    items = []
    for i in ids:
        c = by_id.get(i)
        if not c:
            continue
        items.append(public(c, done.get(i)))
    return {"date": day.isoformat(), "items": items, "done": sum(1 for x in items if x["action"]), "total": len(items),
            "streak": review_streak(conn, settings)}


def public(c, action=None):
    return {"id": c["id"], "text": c["text"], "note": c["note"], "user_note": c.get("user_note"),
            "book_id": c["book_id"], "title": c.get("book_title"), "author": c.get("book_author"),
            "kind": c.get("book_kind"), "source": c["source"], "chapter": c["chapter"], "page": c["page"],
            "created": c["created"], "reviews": c.get("r_reviews") or 0, "action": action,
            "color": c.get("color"), "pos": c.get("pos"), "tags": json.loads(c["r_tags"]) if c.get("r_tags") else [], "fav": bool(c.get("r_fav"))}


def act(conn, settings, hl_id, action, note=None, day=None):
    """day: when it was done (an offline review sent later counts on its own day)."""
    day = day or T.today(settings)
    s = conn.execute("SELECT * FROM review_state WHERE hl_id = ?", (hl_id,)).fetchone()
    interval = s["interval"] if s else 0
    reviews = (s["reviews"] if s else 0) + 1
    if action in ("keep", "note"):
        interval = 4 if interval <= 0 else min(365, round(interval * 2.5))
        status = "kept"
    elif action == "less":
        interval = max(120, interval * 4)
        status = "less"
    elif action == "later":
        interval, status = 1, (s["status"] if s else "kept")
    elif action == "never":
        # Readwise's Discard: the highlight stays in Daf and the vault, and never comes up in review.
        interval, status = 0, "never"
    elif action == "back":
        interval, status = 4, "kept"
    else:
        raise ValueError(action)
    due = (day + timedelta(days=interval)).isoformat() if status != "never" else None
    if s:
        conn.execute("UPDATE review_state SET status = ?, interval = ?, due = ?, reviews = ?, last = ? WHERE hl_id = ?",
                     (status, interval, due, reviews, day.isoformat(), hl_id))
    else:
        conn.execute("INSERT INTO review_state (hl_id, status, interval, due, reviews, last) VALUES (?, ?, ?, ?, ?, ?)",
                     (hl_id, status, interval, due, reviews, day.isoformat()))
    if note is not None:
        set_note(conn, hl_id, note)
    row = conn.execute("SELECT done FROM review_days WHERE day = ?", (day.isoformat(),)).fetchone()
    if row:
        done = json.loads(row["done"])
        done[hl_id] = action
        conn.execute("UPDATE review_days SET done = ? WHERE day = ?", (json.dumps(done), day.isoformat()))
    return {"due": due, "interval": interval}


def _state(conn, hl_id):
    """Make sure a highlight has a review_state row ("noted" keeps it in the fresh pool)."""
    if not conn.execute("SELECT 1 FROM review_state WHERE hl_id = ?", (hl_id,)).fetchone():
        conn.execute("INSERT INTO review_state (hl_id, status, interval, due, reviews) VALUES (?, 'noted', 0, NULL, 0)", (hl_id,))


def clean_tags(tags):
    """Tags as Obsidian writes them: lower case, no spaces or '#', at most 12."""
    out = []
    for t in tags or []:
        t = re.sub(r"[^\w/\-]+", "-", str(t).strip().lstrip("#").lower(), flags=re.U).strip("-")[:40]
        if t and t not in out:
            out.append(t)
    return out[:12]


DOT_TAG = re.compile(r"(?:^|(?<=\s))\.([^\W\d_][\w-]*)")


def dot_tags(text):
    """Readwise's inline tags: ".shame" or ".big-idea" in a note, at the start of a word."""
    return clean_tags(DOT_TAG.findall(text or ""))


def add_tags(conn, hl_id, tags):
    """Add to a highlight's tags (never takes any away)."""
    tags = clean_tags(tags)
    if not tags:
        return None
    _state(conn, hl_id)
    cur = conn.execute("SELECT tags FROM review_state WHERE hl_id = ?", (hl_id,)).fetchone()[0]
    now = json.loads(cur) if cur else []
    merged = clean_tags(now + tags)
    if merged != now:
        conn.execute("UPDATE review_state SET tags = ? WHERE hl_id = ?", (json.dumps(merged), hl_id))
    return merged


def set_tags(conn, hl_id, tags):
    _state(conn, hl_id)
    tags = clean_tags(tags)
    conn.execute("UPDATE review_state SET tags = ?, note_updated = ? WHERE hl_id = ?", (json.dumps(tags) if tags else None, int(time.time()), hl_id))
    return tags


def set_fav(conn, hl_id, fav):
    _state(conn, hl_id)
    conn.execute("UPDATE review_state SET fav = ? WHERE hl_id = ?", (1 if fav else None, hl_id))


def all_tags(conn):
    seen = {}
    for (t,) in conn.execute("SELECT s.tags FROM review_state s JOIN highlights h ON h.id = s.hl_id WHERE s.tags IS NOT NULL AND h.deleted = 0"):
        for x in json.loads(t):
            seen[x] = seen.get(x, 0) + 1
    return sorted(seen, key=lambda k: (-seen[k], k))


def carry(conn, new_id, old_ids, own=("daf", "epub")):
    """A new highlight that swallowed overlapping ones (Daf merges them, like Readwise): the old
    ones go, and their notes, tags, favorite and review history come along."""
    old_ids = [i for i in (old_ids or []) if isinstance(i, str) and i != new_id][:20]
    if not old_ids:
        return
    marks = ",".join("?" * len(old_ids))
    olds = [dict(r) for r in conn.execute(
        f"SELECT h.id, h.color, h.source, s.status, s.interval, s.due, s.reviews, s.last, s.user_note, s.tags, s.fav FROM highlights h "
        f"LEFT JOIN review_state s ON s.hl_id = h.id WHERE h.id IN ({marks}) AND h.deleted = 0", old_ids)]
    olds = [o for o in olds if o["source"] in own]
    if not olds:
        return
    conn.execute(f"UPDATE highlights SET deleted = 1 WHERE id IN ({','.join('?' * len(olds))})", [o["id"] for o in olds])
    notes = [o["user_note"] for o in olds if o["user_note"]]
    tags = [t for o in olds if o["tags"] for t in json.loads(o["tags"])]
    hist = next((o for o in olds if o["status"] and o["status"] != "noted"), None)
    color = next((o["color"] for o in olds if o["color"]), None)
    if color and not conn.execute("SELECT color FROM highlights WHERE id = ?", (new_id,)).fetchone()[0]:
        conn.execute("UPDATE highlights SET color = ? WHERE id = ?", (color, new_id))
    if not (notes or tags or hist or any(o["fav"] for o in olds)):
        return
    _state(conn, new_id)
    cur = conn.execute("SELECT user_note, tags FROM review_state WHERE hl_id = ?", (new_id,)).fetchone()
    note = "\n\n".join(dict.fromkeys(([cur[0]] if cur[0] else []) + notes)) or None
    alltags = clean_tags((json.loads(cur[1]) if cur[1] else []) + tags)
    conn.execute("UPDATE review_state SET user_note = ?, tags = ?, fav = COALESCE(fav, ?) WHERE hl_id = ?",
                 (note, json.dumps(alltags) if alltags else None, 1 if any(o["fav"] for o in olds) else None, new_id))
    if hist:
        conn.execute("UPDATE review_state SET status = ?, interval = ?, due = ?, reviews = ?, last = ? WHERE hl_id = ?",
                     (hist["status"], hist["interval"], hist["due"], hist["reviews"], hist["last"], new_id))


def set_note(conn, hl_id, note):
    note = (note or "").strip() or None
    if conn.execute("SELECT 1 FROM review_state WHERE hl_id = ?", (hl_id,)).fetchone():
        conn.execute("UPDATE review_state SET user_note = ?, note_updated = ? WHERE hl_id = ?", (note, int(time.time()), hl_id))
    else:
        conn.execute("INSERT INTO review_state (hl_id, status, interval, due, reviews, user_note, note_updated) "
                     "VALUES (?, 'noted', 0, NULL, 0, ?, ?)", (hl_id, note, int(time.time())))
