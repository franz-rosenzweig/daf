"""Paper pages: a photo of a marked page in a paper book becomes highlights in that book's note.

Claude (the CLI on the host, with only the Read tool) transcribes the page line by line,
in English or Hebrew, and says which lines carry a pencil mark, underline, bracket or
highlighter, plus any words written in the margin. Marked lines are chosen at once; the
rest can be chosen in Daf (#paper/<id>). Each run of chosen lines is one highlight
(source 'paper') with the page number, written into the book note's Daf region.
"""
import hashlib
import json
import logging
import re
import shutil
import subprocess
import time

from . import config, db, library, secrets, today as T

log = logging.getLogger(__name__)
PAGES = config.STATE / "pages"
CLAUDE = config.CLAUDE

PROMPT = """Read the photo of a book page at {path} with the Read tool.

Transcribe the printed text line by line, exactly as printed (keep the language: English or
Hebrew, with nikud if printed). Skip the running head and the page number in the lines, but
report them separately. For each line say whether the reader marked it: underlined, bracketed
or lined in the margin, highlighted, starred, or circled words. Copy any handwriting in the
margins as margin notes, next to the line they sit beside.

Answer with JSON only, no prose and no code fence:
{{"lang": "en" or "he", "page": printed page number or null, "header": running head text or null,
  "lines": [{{"text": "...", "marked": true or false}}],
  "margin": [{{"line": index of the nearest line, "text": "..."}}]}}"""


def _run_claude(prompt, add_dir, timeout=240):
    r = subprocess.run([CLAUDE, "--print", "--model", secrets.claude_model(), "--allowedTools", "Read", "--add-dir", str(add_dir)],
                       input=prompt, capture_output=True, text=True, timeout=timeout, cwd=str(add_dir))
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        from .ai import plain_error
        raise RuntimeError(plain_error(r.stderr or out))
    return out


def _json(out):
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise ValueError("no JSON in the answer: " + out[:200])
    return json.loads(m.group(0))


def add_photo(conn, src, caption=None):
    """Copy the photo into Daf's state and register the page. Returns its id."""
    PAGES.mkdir(parents=True, exist_ok=True)
    data = open(src, "rb").read()
    pid = "pp" + hashlib.sha1(data).hexdigest()[:14]
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    dest = PAGES / f"{pid}{ext}"
    if not dest.exists():
        shutil.copyfile(src, dest)
    if not conn.execute("SELECT 1 FROM paper_pages WHERE id = ?", (pid,)).fetchone():
        conn.execute("INSERT INTO paper_pages (id, created, photo, caption, status) VALUES (?, ?, ?, ?, 'new')",
                     (pid, int(time.time()), dest.name, (caption or "").strip() or None))
    return pid


def parse_caption(caption):
    """'page', 'p: 112', 'page 112 daring greatly', 'p daring greatly 112' -> (page, title words)."""
    c = re.sub(r"^\s*(?:pages?|p)\b\s*:?\s*", "", caption or "", flags=re.I).strip()
    m = re.search(r"\b(\d{1,4})\b", c)
    page = int(m.group(1)) if m else None
    rest = re.sub(r"\b\d{1,4}\b", " ", c)
    rest = re.sub(r"\s+", " ", rest).strip(" ,.-")
    return page, rest or None


def find_book(conn, words):
    """A book by title words; paper books may only exist as vault notes."""
    if not words:
        return None
    key = library.norm(words)
    best = None
    for r in conn.execute("SELECT id, title, last_read FROM books WHERE kind = 'book'"):
        n = library.norm(r["title"])
        if not n:
            continue
        if n == key or n.startswith(key) or (len(key) >= 5 and key in n):
            score = (n == key, n.startswith(key), r["last_read"] or 0)
            if best is None or score > best[0]:
                best = (score, r["id"])
    return best[1] if best else None


def guess_book(conn, words, header):
    bid = find_book(conn, words) or find_book(conn, header)
    if bid:
        return bid
    # The book of the last paper page, if it was this fortnight.
    r = conn.execute("SELECT book_id FROM paper_pages WHERE book_id IS NOT NULL AND created > ? ORDER BY created DESC LIMIT 1",
                     (int(time.time()) - 14 * 86400,)).fetchone()
    return r[0] if r else None


def read_page(pid):
    """Transcribe with Claude and fill the page row. Marked lines are chosen; returns the row."""
    with db.session() as conn:
        p = conn.execute("SELECT * FROM paper_pages WHERE id = ?", (pid,)).fetchone()
    if not p:
        raise ValueError("no such page")
    try:
        res = _json(_run_claude(PROMPT.format(path=PAGES / p["photo"]), PAGES))
    except Exception as e:  # noqa: BLE001
        with db.session() as conn:
            conn.execute("UPDATE paper_pages SET status = 'error', error = ? WHERE id = ?", (str(e)[:300], pid))
        raise
    lines = [{"text": str(x.get("text", "")).strip(), "marked": bool(x.get("marked"))}
             for x in res.get("lines") or [] if isinstance(x, dict) and str(x.get("text", "")).strip()]
    margin = [m for m in res.get("margin") or [] if isinstance(m, dict) and m.get("text")]
    cap_page, words = parse_caption(p["caption"])
    page = cap_page or (int(res["page"]) if str(res.get("page") or "").isdigit() else None)
    with db.session() as conn:
        book = p["book_id"] or guess_book(conn, words, res.get("header"))
        chosen = [i for i, x in enumerate(lines) if x["marked"]]
        conn.execute("UPDATE paper_pages SET lang = ?, header = ?, page = ?, lines = ?, margin = ?, chosen = ?, book_id = ?, "
                     "status = 'read', error = NULL WHERE id = ?",
                     (res.get("lang") or "en", res.get("header"), page, json.dumps(lines, ensure_ascii=False),
                      json.dumps(margin, ensure_ascii=False), json.dumps(chosen), book, pid))
        if book and chosen:
            save(conn, config.load_settings(), pid, chosen, book, page)
        return dict(conn.execute("SELECT * FROM paper_pages WHERE id = ?", (pid,)).fetchone())


def _join(lines, lang):
    out = ""
    for t in lines:
        if out.endswith("-") and lang != "he" and t[:1].islower():
            out = out[:-1] + t           # a word broken across lines
        else:
            out = (out + " " + t).strip()
    return out


def runs(chosen):
    """[1,2,3,7,8] -> [[1,2,3],[7,8]]"""
    out = []
    for i in sorted(set(chosen)):
        if out and i == out[-1][-1] + 1:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def save(conn, settings, pid, chosen, book_id, page):
    """Replace this page's highlights with one per run of chosen lines, and write the book note."""
    p = conn.execute("SELECT * FROM paper_pages WHERE id = ?", (pid,)).fetchone()
    lines = json.loads(p["lines"] or "[]")
    margin = json.loads(p["margin"] or "[]")
    chosen = [i for i in chosen if isinstance(i, int) and 0 <= i < len(lines)]
    old_books = {r[0] for r in conn.execute("SELECT DISTINCT book_id FROM highlights WHERE source = 'paper' AND pos LIKE ?", (f'%"{pid}"%',))}
    conn.execute("DELETE FROM highlights WHERE source = 'paper' AND pos LIKE ?", (f'%"{pid}"%',))
    made = []
    for run in runs(chosen):
        text = _join([lines[i]["text"] for i in run], p["lang"])
        note = "; ".join(m["text"] for m in margin if isinstance(m.get("line"), int) and run[0] - 1 <= m["line"] <= run[-1] + 1) or None
        hid = "pp" + hashlib.sha1(f"{pid}|{run[0]}|{text}".encode()).hexdigest()[:16]
        conn.execute("INSERT OR REPLACE INTO highlights (id, book_id, source, text, note, chapter, page, created, pos, seen, deleted) "
                     "VALUES (?, ?, 'paper', ?, ?, NULL, ?, ?, ?, ?, 0)",
                     (hid, book_id, text, note, page, p["created"], json.dumps({"pp": pid, "lines": run}), int(time.time())))
        made.append(text)
    conn.execute("UPDATE paper_pages SET chosen = ?, book_id = ?, page = ?, status = 'saved' WHERE id = ?",
                 (json.dumps(sorted(set(chosen))), book_id, page, pid))
    from . import vaultnotes
    res = {}
    for b in {book_id, *old_books} - {None}:
        res[b] = vaultnotes.write_book(conn, settings, b, create=True)
    return made, res


def to_json(row):
    d = dict(row)
    for k in ("lines", "margin", "chosen"):
        d[k] = json.loads(d[k]) if d.get(k) else []
    return d


def from_signal(photo, caption):
    """The Ezer path: read the page now and answer in one message."""
    with db.session() as conn:
        pid = add_photo(conn, photo, caption)
    p = read_page(pid)
    s = config.load_settings()
    base = config.public_url(s)
    with db.session() as conn:
        b = conn.execute("SELECT title FROM books WHERE id = ?", (p["book_id"],)).fetchone() if p["book_id"] else None
    lines = json.loads(p["lines"] or "[]")
    chosen = json.loads(p["chosen"] or "[]")
    where = (f"page {p['page']} of " if p["page"] else "a page of ") + (b["title"].split(":")[0] if b else "a book I couldn't place")
    if not lines:
        return f"I couldn't read any text in that photo. {base}/#paper/{pid}"
    if not chosen:
        return f"Read {where}, {len(lines)} lines, no marks I could see. Pick the lines in Daf: {base}/#paper/{pid}"
    passages = [_join([lines[i]["text"] for i in r], p["lang"]) for r in runs(chosen)]
    n = f"{len(passages)} passage{'s' if len(passages) != 1 else ''}"
    head = f"Saved {n} from {where}" if b else f"Found {n} marked on {where}. Which book is it? Choose it in Daf to save them"
    quoted = "\n\n".join("“" + (t if len(t) < 400 else t[:400] + "…") + "”" for t in passages[:3])
    return f"{head}:\n\n{quoted}\n\nChange the lines or the book: {base}/#paper/{pid}"
