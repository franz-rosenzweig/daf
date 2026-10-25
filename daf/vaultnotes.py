"""Daf's region in book notes: notes added in Daf on highlights, and reading notes
(voice or text) filed under a book.

Daf owns only the text between `<!-- daf -->` and `<!-- daf-end -->`. Everything
else in the note, including koreader-merge's highlight region, stays byte-identical.
Each entry ends with a block id (`^daf-…`). If you edit an entry in Obsidian,
the vault wins: Daf notices the text no longer matches what it last wrote and
takes your version before writing again.
"""
import hashlib
import json
import re
from datetime import datetime

from . import config, today as T

START, END = "<!-- daf -->", "<!-- daf-end -->"
REGION = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
ENTRY = re.compile(r"(?ms)^(?P<body>(?:(?!\^daf-).)*?)\s\^daf-(?P<id>[hn][0-9a-f]{8})\s*$")


def _h(text):
    return hashlib.sha1((text or "").strip().encode()).hexdigest()[:16]


def _short(hid):
    return hashlib.sha1(hid.encode()).hexdigest()[:8]


def _tagged(quote, tags):
    """Tags go on the quote's last line, as Obsidian tags."""
    try:
        tags = json.loads(tags) if isinstance(tags, str) else (tags or [])
    except ValueError:
        tags = []
    return quote + ("".join(" #" + t for t in tags) if tags else "")


def _render(book, hl_notes, reading_notes, settings, listened=()):
    tz = T.tz_of(settings)
    parts = [START, "## From Daf", ""]
    for h in listened:
        try:
            t = json.loads(h["pos"]).get("t") if h["pos"] else None
        except (ValueError, AttributeError):
            t = None
        quote = "\n".join("> " + line for line in (h["text"] or "").strip().splitlines())
        if h.get("source") == "paper":
            label = f"**Paper, p. {h['page']}**" if h.get("page") else "**Paper**"
        elif h.get("source") == "epub":
            label = "**Read in Daf**" + (f" · {h['chapter']}" if h.get("chapter") else "")
        else:
            label = f"**Audiobook, {_ts(t)}**" if t is not None else "**Audiobook**"
        label += f" · {h['note']}" if h.get("note") else ""
        parts += [label, _tagged(quote, h.get("tags")) + f" ^daf-h{_short(h['id'])}", ""]
    for h in hl_notes:
        quote = _tagged("\n".join("> " + line for line in (h["text"] or "").strip().splitlines()), h.get("tags"))
        if h["user_note"]:
            parts += [quote, "", f"{h['user_note'].strip()} ^daf-h{_short(h['id'])}", ""]
        else:
            parts += [quote + f" ^daf-h{_short(h['id'])}", ""]
    for n in reading_notes:
        when = datetime.fromtimestamp(n["created"], tz).strftime("%Y-%m-%d %H:%M")
        where = f" · page {n['page']} of {n['total']}" if n["page"] and n["total"] else ""
        kind = "voice note" if n["source"] == "voice" else "note"
        parts += [f"**{when}{where}** · {kind}", f"{n['text'].strip()} ^daf-n{_short(n['id'])}", ""]
    parts.append(END)
    return "\n".join(parts)


def _existing_entries(region_text):
    """block id -> the note text you see for it now."""
    out = {}
    for m in ENTRY.finditer(region_text):
        body = m.group("body").rstrip()
        lines = body.splitlines()
        # The note is the last paragraph before the block id (after the quote or the header line).
        para = []
        for line in reversed(lines):
            if not line.strip() or line.startswith(">") or line.startswith("**") or line.startswith("## ") or line.startswith("<!--"):
                break
            para.insert(0, line)
        out[m.group("id")] = "\n".join(para).strip()
    return out


def new_book_note(conn, b):
    """A minimal book note, for a paper book that had none (the Hardcover import fills the rest)."""
    name = _clip_name(f"📚 {b['title'].split(':')[0]}" + (f" ({b['author']})" if b["author"] else ""))
    rel = f"Reference/books/{name}.md"
    if (config.VAULT / rel).exists():
        conn.execute("UPDATE books SET vault_path = ? WHERE id = ?", (rel, b["id"]))
        return rel
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    (config.VAULT / "Reference" / "books").mkdir(parents=True, exist_ok=True)
    (config.VAULT / rel).write_text(
        "---\ntype: book\n" f"title: {_yaml(b['title'])}\nauthor: {_yaml(b['author'])}\n"
        'categories: "[[Books]]"\ntags:\n  - books\n  - references\n'
        f"created: {now}\nstatus: reading\nformat: paper\ndatasource: daf\n---\n"
        f"# {b['title']}\n\n", encoding="utf-8")
    conn.execute("UPDATE books SET vault_path = ? WHERE id = ?", (rel, b["id"]))
    return rel


def write_book(conn, settings, book_id, create=False):
    """Rewrite one book note's Daf region. Returns 'written', 'unchanged' or a reason it was skipped.
    With create, a book without a vault note gets one (paper pages)."""
    b = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not b:
        return "no such book"
    if not b["vault_path"] or not (config.VAULT / b["vault_path"]).exists():
        if not create or b["kind"] != "book" or b["private"]:
            return "no vault note"
        new_book_note(conn, b)
        b = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    path = config.VAULT / b["vault_path"]
    # Highlights with a note from Daf (or tags, for ones Daf doesn't list on its own). One that was
    # removed in Daf, or merged into a bigger one, goes; a Kindle one deleted on the Kindle keeps its note.
    hl_notes = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, s.user_note, s.vault_hash, s.tags FROM highlights h JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.book_id = ? AND (s.user_note IS NOT NULL OR (s.tags IS NOT NULL AND h.source NOT IN ('audiobookshelf', 'paper', 'epub') AND h.deleted = 0)) "
        "AND NOT (h.deleted = 1 AND h.source IN ('epub', 'paper', 'daf')) ORDER BY COALESCE(h.page, 0), h.created", (book_id,))]
    listened = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.note, h.pos, h.source, h.page, h.chapter, s.tags FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.book_id = ? AND h.source IN ('audiobookshelf', 'paper', 'epub') "
        "AND h.deleted = 0 AND s.user_note IS NULL "
        "ORDER BY h.source, COALESCE(h.page, 0), h.created", (book_id,))]
    notes = [dict(r) for r in conn.execute(
        "SELECT * FROM reading_notes WHERE book_id = ? ORDER BY created", (book_id,))]
    text = path.read_text(encoding="utf-8")
    m = REGION.search(text)
    if m:
        # Vault wins: adopt any entry edited in Obsidian since Daf last wrote it.
        current = _existing_entries(m.group(0))
        for h in hl_notes:
            v = current.get("h" + _short(h["id"]))
            if v and h["vault_hash"] and _h(v) != h["vault_hash"] and _h(v) != _h(h["user_note"]):
                h["user_note"] = v
                conn.execute("UPDATE review_state SET user_note = ? WHERE hl_id = ?", (v, h["id"]))
        for n in notes:
            v = current.get("n" + _short(n["id"]))
            if v is not None and n["vault_hash"] and _h(v) != n["vault_hash"] and _h(v) != _h(n["text"]):
                n["text"] = v
                conn.execute("UPDATE reading_notes SET text = ? WHERE id = ?", (v, n["id"]))
    if not hl_notes and not notes and not listened and not m:
        return "nothing to write"
    region = _render(b, hl_notes, notes, settings, listened)
    if m:
        new = text[:m.start()] + region + text[m.end():]
    else:
        new = text.rstrip("\n") + "\n\n" + region + "\n"
    if new != text:
        tmp = path.with_name(f".{path.name}.daf-tmp")
        tmp.write_text(new, encoding="utf-8")
        tmp.replace(path)
    for h in hl_notes:
        conn.execute("UPDATE review_state SET vault_hash = ? WHERE hl_id = ?", (_h(h["user_note"]), h["id"]))
    for n in notes:
        conn.execute("UPDATE reading_notes SET vault_hash = ? WHERE id = ?", (_h(n["text"]), n["id"]))
    return "written" if new != text else "unchanged"


def write_all(conn, settings):
    ids = {r[0] for r in conn.execute(
        "SELECT DISTINCT h.book_id FROM highlights h JOIN review_state s ON s.hl_id = h.id WHERE s.user_note IS NOT NULL "
        "AND h.source NOT IN ('daf', 'clip')")}
    ids |= {r[0] for r in conn.execute("SELECT DISTINCT book_id FROM highlights WHERE source IN ('audiobookshelf', 'paper', 'epub') AND deleted = 0 AND book_id IS NOT NULL")}
    ids |= {r[0] for r in conn.execute("SELECT DISTINCT book_id FROM reading_notes WHERE book_id IS NOT NULL")}
    # Articles highlighted on the Kindle (Send to Kindle): their clipping notes. Any id that is a
    # document (an article's Karakeep highlight with a note, say) gets its clipping note, never a
    # book note's region, which would leave only the noted highlights in it.
    ids |= {r[0] for r in conn.execute("SELECT DISTINCT h.book_id FROM highlights h JOIN docs d ON d.id = h.book_id WHERE h.source = 'kindle'")}
    docs = {r[0] for r in conn.execute("SELECT id FROM docs WHERE id IN (%s)" % ",".join("?" * len(ids)), tuple(ids))} if ids else set()
    out = {bid: write_book(conn, settings, bid) for bid in ids - docs if bid}
    out.update({doc: write_article(conn, settings, doc) for doc in docs})
    return out


def write_for(conn, settings, book_id):
    """The note a highlight's change belongs in: an article's clipping note (anything in docs), or a
    book's note. Every place that rewrites a note after a highlight changes goes through here."""
    if not book_id:
        return "no book"
    if conn.execute("SELECT 1 FROM docs WHERE id = ?", (book_id,)).fetchone():
        return write_article(conn, settings, book_id)
    return write_book(conn, settings, book_id)


# ---- articles: one clipping note per article with highlights ---------------------

CLIP_DIR = "Reference/clippings"


def _clip_name(title):
    """A file name from a title: at most 120 characters and 200 bytes (Hebrew, CJK and emoji take
    more than one byte each, and the file system allows 255 with ".md" and " (2)")."""
    t = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", title or "Untitled")
    t = re.sub(r"\s+", " ", t).strip()[:120]
    while len(t.encode()) > 200:
        t = t[:-1]
    return t.strip() or "Untitled"


def _yaml(v):
    v = (v or "").replace("\n", " ").strip()
    return '"' + v.replace('"', "'") + '"' if v else '""'


def _ts(t):
    t = int(t or 0)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


FOLDERS = {"video": "Reference/youtube", "podcast": "Reference/podcasts", "torah": "Reference/torah"}


def write_article(conn, settings, doc_id):
    """Create or update the note for an article, video or podcast episode with highlights in Daf.
    Daf owns its region; the head is written once."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    b = conn.execute("SELECT * FROM books WHERE id = ?", (doc_id,)).fetchone()
    if not d and not b:
        return "no doc"
    m_ = {"title": (d or b)["title"], "url": d["url"] if d else b["url"], "author": (d["author"] if d else b["author"]) or "",
          "source": d["source"] if d else (b["author"] or ""), "published": d["published"] if d else None,
          "kind": d["kind"] if d else b["kind"], "note": d["note"] if d else None}
    hls = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.pos, CASE WHEN h.source = 'kindle' THEN COALESCE(s.user_note, h.note) ELSE s.user_note END AS user_note, "
        "s.vault_hash, s.tags FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.book_id = ? AND h.deleted = 0 AND h.source IN ('daf', 'clip', 'kindle') ORDER BY h.created", (doc_id,))]
    rel = b["vault_path"] if b and b["vault_path"] else None
    if rel and not (config.VAULT / rel).exists():
        rel = None
    if not hls and not m_["note"] and not rel:       # a note already written still loses its last highlight
        return "nothing to write"
    from . import social
    reel = m_["kind"] == "video" and social.is_reel(m_["url"])     # an Instagram reel: beside the YouTube notes, its own folder
    if not rel:
        folder = "Reference/instagram" if reel else FOLDERS.get(m_["kind"], CLIP_DIR)
        base = _clip_name(m_["title"])
        rel = f"{folder}/{base}.md"
        n = 2
        while (config.VAULT / rel).exists():
            rel = f"{folder}/{base} ({n}).md"
            n += 1
        published = datetime.fromtimestamp(m_["published"]).strftime("%Y-%m-%d") if m_["published"] else ""
        tags = {"video": "  - clippings\n  - youtube\n  - videos\n", "podcast": "  - clippings\n  - podcasts\n",
                "torah": "  - clippings\n  - torah\n"}.get(m_["kind"], "  - clippings\n")
        if reel:
            tags = "  - clippings\n  - instagram\n  - videos\n"
        head = ("---\ntags:\n" + tags + "datasource: daf\n"
                f"url: {_yaml(m_['url'])}\nauthor: {_yaml(m_['author'])}\nsource: {_yaml(m_['source'])}\n"
                + (f"published: {published}\n" if published else "") + "---\n#ai-assisted-note\n"
                f"# {m_['title']}\n\n## Data\n- SOURCE: {m_['url'] or ''}\n" + (f"- Published: {published}\n" if published else "")
                + "\n---\n\n")
        (config.VAULT / folder).mkdir(parents=True, exist_ok=True)
        (config.VAULT / rel).write_text(head + START + "\n" + END + "\n", encoding="utf-8")
        conn.execute("UPDATE books SET vault_path = ? WHERE id = ?", (rel, doc_id))
    path = config.VAULT / rel
    text = path.read_text(encoding="utf-8")
    m = REGION.search(text)
    if m:
        current = _existing_entries(m.group(0))
        for h in hls:
            v = current.get("h" + _short(h["id"]))
            if v and h["vault_hash"] and _h(v) != h["vault_hash"] and _h(v) != _h(h["user_note"]):
                h["user_note"] = v
                conn.execute("UPDATE review_state SET user_note = ? WHERE hl_id = ?", (v, h["id"]))
    verses, book = {}, None
    if m_["kind"] == "torah" and d:
        row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
        verses = {i: b.get("n") for i, b in enumerate(json.loads(row[0]))} if row else {}
        mb = re.match(r"^(.*?)\s+\d", d["summary"] or "")
        book = mb.group(1) if mb else None
    parts = [START]
    if m_["note"]:
        parts += [f"**Notes:** {m_['note'].strip()}", ""]
    parts += ["## Highlights", ""]
    for h in hls:
        try:
            pos = json.loads(h["pos"]) if h["pos"] else {}
        except ValueError:
            pos = {}
        when = f" ({_ts(pos['t'])})" if isinstance(pos, dict) and pos.get("t") is not None else ""
        if verses and isinstance(pos, dict) and verses.get(pos.get("b")):
            when = f" ({book + ' ' if book else ''}{verses[pos['b']]})"
        quote = _tagged("\n".join("> " + line for line in (h["text"] or "").strip().splitlines()) + when, h.get("tags"))
        if h["user_note"]:
            parts += [quote, "", f"{h['user_note'].strip()} ^daf-h{_short(h['id'])}", ""]
        else:
            parts += [quote + f" ^daf-h{_short(h['id'])}", ""]
    parts.append(END)
    region = "\n".join(parts)
    new = text[:m.start()] + region + text[m.end():] if m else text.rstrip("\n") + "\n\n" + region + "\n"
    if new != text:
        tmp = path.with_name(f".{path.name}.daf-tmp")
        tmp.write_text(new, encoding="utf-8")
        tmp.replace(path)
    for h in hls:
        if h["user_note"]:
            conn.execute("UPDATE review_state SET vault_hash = ? WHERE hl_id = ?", (_h(h["user_note"]), h["id"]))
    return "written" if new != text else "unchanged"
