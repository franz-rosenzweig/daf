"""Notes that arrive from Ezer: a reply to the morning highlight, or a thought
while reading (typed or a voice note), filed under the book open on the Kindle.

Where a note goes:
1. It starts with "n:"/"note:" and a morning highlight went out in the last 20 hours
   that has no note yet: under that highlight.
2. Otherwise, the Kindle has been read in the last 3 hours, or the note says "note"
   or "reading": a reading note on that book, at that page.
3. Otherwise it isn't filed, and the reply says how to file it.
"""
import hashlib
import json
import re
import subprocess
import time

from . import library, review, vaultnotes

TRANSCRIBE = "/srv/office/bin/transcribe"
RECENT_READING = 3 * 3600
MORNING_WINDOW = 20 * 3600


def _kv(conn, k, v=None):
    if v is None:
        r = conn.execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
        return json.loads(r[0]) if r else None
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, json.dumps(v)))


def remember_morning(conn, hl_id):
    _kv(conn, "morning", {"id": hl_id, "at": int(time.time())})


def add_reading_note(conn, settings, book_id, text, page=None, total=None, source="text"):
    nid = hashlib.sha1(f"{book_id}|{time.time()}|{text}".encode()).hexdigest()[:16]
    conn.execute("INSERT INTO reading_notes (id, book_id, page, total, text, created, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (nid, book_id, page, total, text.strip(), int(time.time()), source))
    return nid, vaultnotes.write_for(conn, settings, book_id)


def file_note(conn, settings, text, source="text", explicit=False):
    """Returns a one-line reply for Signal."""
    text = re.sub(r"^\s*(n|note|daf)\s*[:\-]\s*", "", text.strip(), flags=re.I) if explicit else text.strip()
    if not text:
        return "That note was empty."
    m = _kv(conn, "morning")
    if explicit and m and time.time() - m["at"] < MORNING_WINDOW:
        has = conn.execute("SELECT user_note FROM review_state WHERE hl_id = ?", (m["id"],)).fetchone()
        if not (has and has[0]):
            review.act(conn, settings, m["id"], "note", note=text)
            h = conn.execute("SELECT b.title, b.id FROM highlights h LEFT JOIN books b ON b.id = h.book_id WHERE h.id = ?", (m["id"],)).fetchone()
            res = vaultnotes.write_for(conn, settings, h["id"]) if h and h["id"] else "no vault note"
            where = "in the vault note" if res in ("written", "unchanged") else "in Daf (that book has no vault note)"
            return f"Saved under this morning's highlight from {h['title'] if h else 'your library'}, {where}."
    cur = library.current_kindle_book(conn)
    mentions = bool(re.match(r"^\s*(note|reading|reading note)\b", text, re.I))
    if cur and cur["book"] and (explicit or mentions or time.time() - cur["when"] < RECENT_READING):
        b = cur["book"]
        text = re.sub(r"^\s*(reading note|note|reading)\s*[:,.\-]?\s*", "", text, flags=re.I) if mentions else text
        _nid, res = add_reading_note(conn, settings, b["id"], text, cur["page"], cur["total"], source)
        where = f", page {cur['page']}" if cur["page"] else ""
        filed = "in the vault note" if res in ("written", "unchanged") else "in Daf (no vault note for this book yet)"
        title = "a private book" if b["private"] else b["title"].split(":")[0]
        return f"Filed under {title}{where}, {filed}."
    return ("Not filed: nothing read on the Kindle in the last 3 hours. "
            "Start it with \"note:\" to put it under the book you read last.")


def transcribe(path):
    out = subprocess.run([TRANSCRIBE, path], capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "transcription failed").strip()[-200:])
    lines = [x for x in out.stdout.strip().splitlines() if x.strip()]
    # First line is a language tag like "[en 0.98 small]"; the rest is the text.
    if lines and lines[0].startswith("[") and lines[0].endswith("]"):
        lines = lines[1:]
    text = " ".join(lines).strip()
    return "" if text == "(nothing intelligible)" else text
