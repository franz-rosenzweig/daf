"""Flashcards from highlights (Readwise calls it Mastery).

A card is a cloze (the highlight with words hidden, marked {{like this}} in `front`) or a
question and answer. Due cards join the daily review after its highlights; each answer is
graded Again / Hard / Good / Easy and the next date follows from it, roughly as Anki does:
a new card comes back in a day (four if Easy), then the interval grows by the card's ease.
"""
import hashlib
import json
import re
import time
from datetime import timedelta

from . import today as T

CLOZE = re.compile(r"\{\{(.+?)\}\}", re.S)
GRADES = {"again": 1, "hard": 2, "good": 3, "easy": 4}


def _row(r):
    d = dict(r)
    d["blanks"] = CLOZE.findall(d["front"]) if d["kind"] == "cloze" else []
    return d


def for_highlight(conn, hl_id):
    return [_row(r) for r in conn.execute("SELECT * FROM cards WHERE hl_id = ? ORDER BY created", (hl_id,))]


def save(conn, hl_id, kind, front, back=None, card_id=None):
    if kind not in ("cloze", "qa"):
        raise ValueError("cloze or qa")
    front = (front or "").strip()
    back = (back or "").strip() or None
    if kind == "cloze" and not CLOZE.search(front):
        raise ValueError("Hide at least one word")
    if kind == "qa" and (not front or not back):
        raise ValueError("A question and an answer, please")
    h = conn.execute("SELECT id FROM highlights WHERE id = ?", (hl_id,)).fetchone()
    if not h:
        raise ValueError("No such highlight")
    now = int(time.time())
    if card_id:
        conn.execute("UPDATE cards SET kind = ?, front = ?, back = ? WHERE id = ? AND hl_id = ?", (kind, front, back, card_id, hl_id))
        return card_id
    cid = "c" + hashlib.sha1(f"{hl_id}|{now}|{front}".encode()).hexdigest()[:15]
    conn.execute("INSERT INTO cards (id, hl_id, kind, front, back, created, due, interval, ease, reps, lapses) "
                 "VALUES (?, ?, ?, ?, ?, ?, NULL, 0, 2.5, 0, 0)", (cid, hl_id, kind, front, back, now))
    return cid


def delete(conn, card_id):
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))


def due(conn, settings, day=None):
    """Cards due today: every review that's due, plus up to cards_per_day new ones."""
    day = day or T.today(settings)
    key = day.isoformat()
    q = ("SELECT c.*, h.text AS hl_text, h.book_id, h.chapter, h.page, b.title, b.author FROM cards c "
         "JOIN highlights h ON h.id = c.hl_id LEFT JOIN books b ON b.id = h.book_id WHERE c.suspended IS NULL AND h.deleted = 0 ")
    reviews = [_row(r) for r in conn.execute(q + "AND c.due IS NOT NULL AND c.due <= ? ORDER BY c.due LIMIT 40", (key,))]
    # New cards seen today count against the daily allowance.
    seen_new = conn.execute("SELECT COUNT(*) FROM cards WHERE first_seen = ?", (key,)).fetchone()[0]
    n_new = max(0, int(settings.get("cards_per_day", 5)) - seen_new)
    new = [_row(r) for r in conn.execute(q + "AND c.due IS NULL ORDER BY c.created LIMIT ?", (n_new,))] if n_new else []
    return reviews + new


def grade(conn, settings, card_id, g):
    """Schedule a card after an answer. Returns the next due date."""
    g = GRADES.get(g, g)
    if g not in (1, 2, 3, 4):
        raise ValueError("again, hard, good or easy")
    c = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    if not c:
        raise ValueError("No such card")
    day = T.today(settings)
    ease, interval, reps, lapses = c["ease"] or 2.5, c["interval"] or 0, c["reps"] or 0, c["lapses"] or 0
    if reps == 0:
        interval = {1: 0, 2: 1, 3: 1, 4: 4}[g]
    elif g == 1:
        interval, ease, lapses = 1, max(1.3, ease - 0.2), lapses + 1
    elif g == 2:
        interval, ease = max(1, round(interval * 1.2)), max(1.3, ease - 0.15)
    elif g == 3:
        interval = max(interval + 1, round(interval * ease))
    else:
        interval, ease = max(interval + 2, round(interval * ease * 1.3)), ease + 0.15
    due_day = (day + timedelta(days=interval)).isoformat()
    conn.execute("UPDATE cards SET interval = ?, ease = ?, reps = ?, lapses = ?, due = ?, last = ?, "
                 "first_seen = COALESCE(first_seen, ?) WHERE id = ?",
                 (interval, round(ease, 2), reps + 1, lapses, due_day, day.isoformat(), day.isoformat(), card_id))
    return {"due": due_day, "interval": interval}


def counts(conn, settings):
    day = T.today(settings).isoformat()
    total = conn.execute("SELECT COUNT(*) FROM cards c JOIN highlights h ON h.id = c.hl_id WHERE h.deleted = 0").fetchone()[0]
    return {"total": total, "due": len(due(conn, settings)), "today": day}


def suggest(conn, hl_id):
    """The model proposes a cloze and a question for a highlight (Preferences → AI → Flashcards)."""
    h = conn.execute("SELECT h.text, h.chapter, b.title, b.author FROM highlights h LEFT JOIN books b ON b.id = h.book_id WHERE h.id = ?",
                     (hl_id,)).fetchone()
    if not h:
        raise ValueError("No such highlight")
    from . import ai
    prompt = (
        ai.prompt("card") + " Answer with JSON only, "
        'no prose: {"cloze": "<the highlight, word for word, with the one to four words that carry the idea wrapped in '
        '{{ and }}>", "question": "<a short question whose answer is the idea>", "answer": "<a short answer, in the '
        'highlight\'s own words where it can>"}. Keep the highlight\'s language.\n\n'
        f"Book: {h['title'] or ''} ({h['author'] or ''}){' · ' + h['chapter'] if h['chapter'] else ''}\nHighlight: {h['text']}"
    )
    out = ai.run(prompt, timeout=120)
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise RuntimeError("No suggestion came back")
    d = json.loads(m.group(0))
    return {k: str(d.get(k) or "").strip() for k in ("cloze", "question", "answer")}
