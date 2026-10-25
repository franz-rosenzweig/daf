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
from urllib.parse import quote, urlparse

from . import config, today as T, vaultmd

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
CATEGORY = {"video": "video", "podcast": "podcast", "tweet": "tweet", "pdf": "pdf", "torah": "torah"}
# The vault's Bases list clippings by these (Templates/Bases/Clippings.base, Youtube Clippings.base, Podcast episodes.base).
CATEGORIES = {"video": "Youtube Clippings", "podcast": "Podcast episodes"}
TAGS = {"video": ["clippings", "youtube", "videos"], "podcast": ["clippings", "podcasts"], "torah": ["clippings", "torah"],
        "reel": ["clippings", "instagram", "videos"]}
# Frontmatter keys Daf never writes: hardcover-sync and koreader-merge keep these in book notes, and
# Obsidian adds created/updated itself (the vault's linter strips them).
NOT_DAFS = {"status", "rating", "read", "consuming", "progress", "review", "created", "updated"}
SOURCES = ("daf", "clip", "kindle", "karakeep")
# Where the text starts in Daf's region; the notes and highlights above it are what flows back from the vault.
TEXT_HEADS = re.compile(r"(?m)^## (?:Full text|Transcript|Caption|Show notes)$")
DOCNOTE = re.compile(r"(?ms)^## Notes\n\n(?P<body>.*?)\s\^daf-note[ \t]*$")


def daf_link(settings, doc_id, doc=True):
    """The document in Daf (the reading view), or a podcast clip's page."""
    return f"{config.public_url(settings)}/#{'read' if doc else 'book'}/{quote(doc_id, safe='')}"


def _tweet_title(title):
    """'Name on X: "the post…" / X' (as X titles its pages) → 'Name on X: the post…', shorter."""
    m = re.match(r'^(?:\(\d+\)\s*)?(.+?) on X:\s*["“]([\s\S]*?)(?:["”]\s*/\s*X)?$', title or "")
    if not m:
        return title
    lead = re.sub(r"\s+", " ", m.group(2)).strip()
    if len(lead) > 80:
        lead = lead[:80].rsplit(" ", 1)[0] + "…"
    return f"{m.group(1)} on X: {lead}" if lead else f"{m.group(1)} on X"


def _authors(author, category=None):
    """The names in an author line, one [[link]] each, as the Web Clipper writes them. A Torah
    reading's "author" (Torah, Haftarah) isn't a person."""
    a = re.sub(r"^(by|von|par)\s+", "", (author or "").strip(), flags=re.I)
    if not a or category == "torah":
        return []
    parts = [p.strip() for p in re.split(r"\s*(?:;|&|\band\b)\s*", a) if p.strip()]
    out = []
    for p in parts:
        bits = [x.strip() for x in p.split(",") if x.strip()]
        if len(bits) > 1 and any(len(x.split()) < 2 for x in bits):
            out.append(p)                          # "Doe, Jane" or "Smith, Jr.": one name
        elif len(bits) > 1 and any(AFFIL.search(x) for x in bits[1:]):
            out.append(bits[0])                    # "Jane Doe, Professor of History, Some University"
        else:
            out += bits
    return [n for n in (re.sub(r"[\[\]|#^]+", "", p).strip() for p in out[:6]) if n]


AFFIL = re.compile(r"\b(of|at|for|the|University|College|Institute|School|Professor|Lecturer|Fellow|Editor|Reporter|"
                   r"Correspondent|Staff|Writer|Contributor|Director|Researcher|Candidate|Student)\b")


def _date(ts, settings):
    return datetime.fromtimestamp(ts, T.tz_of(settings)).strftime("%Y-%m-%d") if ts else ""


def _article(conn, settings, doc_id):
    """What a note says about a document (or a podcast clip's episode, which is only a books row)."""
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    b = conn.execute("SELECT * FROM books WHERE id = ?", (doc_id,)).fetchone()
    if not d and not b:
        return None
    from . import media, social
    r = d or b
    kind, url = r["kind"], r["url"]
    reel = kind == "video" and social.is_reel(url)
    title = (r["title"] or "").strip() or url or "Untitled"
    if kind == "tweet":
        title = _tweet_title(title)
    yt = media.youtube_id(url) if kind == "video" and url and not reel else None
    thumb = d["thumb"] if d and (d["thumb"] or "").startswith(("http://", "https://")) else None
    return {"id": doc_id, "doc": bool(d), "title": title, "url": url or "", "kind": kind,
            "author": (d["author"] if d else b["author"]) or "", "source": (d["source"] if d else b["author"]) or "",
            "published": d["published"] if d else None, "saved": d["added"] if d else None, "words": d["words"] if d else None,
            "category": "reel" if reel else CATEGORY.get(kind, "article"), "note": d["note"] if d else None,
            "cover": f"https://i.ytimg.com/vi/{yt}/maxresdefault.jpg" if yt else thumb,
            "daf": daf_link(settings, doc_id, bool(d)), "summary": d["summary"] if d else None}


def _fm(m, settings):
    """Daf's frontmatter keys for a note, in order: [(key, YAML value)]."""
    out = [("title", _yaml(m["title"]))]
    names = _authors(m["author"], m["category"])
    if names:
        out.append(("author", "".join(f'\n  - "[[{n}]]"' for n in names)))
    out += [("url", _yaml(m["url"])), ("daf", _yaml(m["daf"])), ("source", _yaml(m["source"])), ("category", m["category"])]
    if m["published"]:
        out.append(("published", _date(m["published"], settings)))
    if m["saved"]:
        out.append(("saved", _date(m["saved"], settings)))
    if m["words"]:
        out.append(("words", str(int(m["words"]))))
    if m["cover"]:
        out.append(("cover", _yaml(m["cover"])))
    out.append(("categories", f'\n  - "[[{CATEGORIES.get(m["category"], "Clippings")}]]"'))
    show = re.sub(r"[\[\]|#^]+", "", m["source"]).strip()
    if m["category"] == "podcast" and show:
        out.append(("show", f'"[[{show}]]"'))
    return [(k, v) for k, v in out if k not in NOT_DAFS]


def _fm_text(pairs):
    return "".join(f"{k}:{v if v.startswith(chr(10)) else ' ' + v}\n" for k, v in pairs)


def _new_note(m, settings):
    tags = "".join(f"  - {t}\n" for t in TAGS.get(m["category"], ["clippings"]))
    return ("---\n" + _fm_text(_fm(m, settings)) + "tags:\n" + tags + "datasource: daf\n---\n#ai-assisted-note\n"
            f"# {vaultmd._esc(m['title'])}\n\n" + START + "\n" + END + "\n")


def _frontmatter(text):
    """(start, end) of the frontmatter's lines, or None."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    return (4, end + 1) if end >= 0 else None


def _own(text):
    """A note Daf made (the full text goes only into those, never into a Readwise note or a vault essay)."""
    f = _frontmatter(text)
    return bool(f) and re.search(r"(?m)^datasource: daf\s*$", text[f[0]:f[1]]) is not None


def _fill_head(text, m, settings):
    """A note an older Daf made: the keys it lacks are added. Nothing already there changes."""
    f = _frontmatter(text)
    if not f:
        return text
    have = set(re.findall(r"(?m)^([A-Za-z_][\w-]*):", text[f[0]:f[1]]))
    add = _fm_text([(k, v) for k, v in _fm(m, settings) if k not in have])
    return text[:f[1]] + add + text[f[1]:] if add else text


def _keep_daf_link(text, m, settings):
    """The `daf:` address follows the document (a Feed item saved to the Library gets a new id)."""
    f = _frontmatter(text)
    if not f:
        return text
    fm = text[f[0]:f[1]]
    new = re.sub(r'(?m)^daf: "?' + re.escape(config.public_url(settings)) + r'/#[^"\n]*"?$', lambda _: "daf: " + _yaml(m["daf"]), fm, count=1)
    return text[:f[0]] + new + text[f[1]:]


def _quote(h, loc, anchor):
    text = (h["text"] or "").strip()
    if not re.match(r"^!\[[^\]]*\]\(\S+\)$", text):         # a picture's highlight is its Markdown already
        text = vaultmd._esc(text)
    q = "\n".join("> " + vaultmd._line_start(line) for line in text.splitlines())
    if anchor is not None:
        q += f" ([[#^daf-b{anchor}|{loc or 'in the text'}]])"
    elif loc:
        q += f" ({loc})"
    return _tagged(q, h.get("tags"))


def _text_sections(m, doc):
    cues = any(b.get("t") == "cue" for b in doc.blocks)
    if m["category"] == "reel":                   # the caption, then "Transcript" and its lines (social.fetch)
        k = next((i for i, b in enumerate(doc.blocks) if b.get("t") == "h3" and b.get("x") == "Transcript"), len(doc.blocks))
        cap, tr = doc.markdown(m["daf"], hi=k), doc.markdown(m["daf"], lo=k + 1)
        return (["## Caption", "", cap, ""] if cap else []) + (["## Transcript", "", tr, ""] if tr else [])
    md = doc.markdown(m["daf"])
    head = "## Transcript" if cues else "## Show notes" if m["category"] == "podcast" else "## Full text"
    return [head, "", md, ""] if md else []


KARAKEEP_DIR = "Reference/karakeep"              # karakeep-sync.py's notes, from before Daf kept the Library


def _karakeep_note(doc_id):
    """The note karakeep-sync.py made for a bookmark (`id:` in its frontmatter), so a Karakeep-era
    article gets Daf's region there instead of a second note."""
    root = config.VAULT / KARAKEEP_DIR
    if not doc_id.startswith("kk:") or not root.is_dir():
        return None
    want = re.compile(r"(?m)^id: " + re.escape(doc_id[3:]) + r"\s*$")
    for p in sorted(root.rglob("*.md")):
        try:
            if want.search(p.read_text(encoding="utf-8")[:2000]):
                return str(p.relative_to(config.VAULT))
        except (OSError, UnicodeDecodeError):
            continue
    return None


def write_article(conn, settings, doc_id, backfill=False):
    """Create or update the note for an article, video, podcast episode, tweet, PDF, reel or Torah
    reading with highlights or a note in Daf. Daf owns its region (where the full text goes, in notes
    it made itself); the head is written once, and only the `daf:` link follows the document after
    that. backfill: a note an older Daf made also gets the frontmatter keys it lacks."""
    m_ = _article(conn, settings, doc_id)
    if not m_:
        return "no doc"
    hls = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.pos, h.created, h.source, CASE WHEN h.source = 'kindle' THEN COALESCE(s.user_note, h.note) ELSE s.user_note END AS user_note, "
        "s.vault_hash, s.tags FROM highlights h LEFT JOIN review_state s ON s.hl_id = h.id "
        "WHERE h.book_id = ? AND h.deleted = 0 AND h.source IN (%s) ORDER BY h.created" % ",".join("?" * len(SOURCES)), (doc_id, *SOURCES))]
    b = conn.execute("SELECT vault_path FROM books WHERE id = ?", (doc_id,)).fetchone()
    if not b and m_["doc"]:
        from . import reader
        reader._ensure_book(conn, conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone())
    rel = b["vault_path"] if b and b["vault_path"] else None
    if rel and not (config.VAULT / rel).exists():
        rel = None
    if not hls and not m_["note"] and not rel:       # a note already written still loses its last highlight
        return "nothing to write"
    if not rel and (rel := _karakeep_note(doc_id)):
        conn.execute("UPDATE books SET vault_path = ? WHERE id = ?", (rel, doc_id))
    if not rel:
        folder = "Reference/instagram" if m_["category"] == "reel" else FOLDERS.get(m_["kind"], CLIP_DIR)
        base = _clip_name(m_["title"])
        rel = f"{folder}/{base}.md"
        n = 2
        while (config.VAULT / rel).exists():
            rel = f"{folder}/{base} ({n}).md"
            n += 1
        (config.VAULT / folder).mkdir(parents=True, exist_ok=True)
        (config.VAULT / rel).write_text(_new_note(m_, settings), encoding="utf-8")
        conn.execute("UPDATE books SET vault_path = ? WHERE id = ?", (rel, doc_id))
    path = config.VAULT / rel
    text = path.read_text(encoding="utf-8")
    m = REGION.search(text)
    own = _own(text)
    note = m_["note"]
    if not own:
        # A note from before Daf kept the Library (Karakeep's) has their highlights and note already.
        hls = [h for h in hls if h["source"] != "karakeep"]
        outside = text[:m.start()] + text[m.end():] if m else text
        if note and note.strip() in outside:
            note = None
    if not m and not hls and not note:                # a note of yours Daf has never written in (a vault essay opened in Daf)
        return "nothing to write"
    kept_note = conn.execute("SELECT v FROM kv WHERE k = ?", ("vault_note:" + doc_id,)).fetchone()
    if m:
        # Vault wins: a note on a highlight, or the document's note, edited in Obsidian since Daf wrote it.
        top = m.group(0)
        t = TEXT_HEADS.search(top)
        top = top[:t.start()] if t else top
        current = _existing_entries(top)
        for h in hls:
            v = current.get("h" + _short(h["id"]))
            if v and h["vault_hash"] and _h(v) != h["vault_hash"] and _h(v) != _h(h["user_note"]):
                h["user_note"] = v
                conn.execute("UPDATE review_state SET user_note = ? WHERE hl_id = ?", (v, h["id"]))
        dn = DOCNOTE.search(top)
        if dn and m_["doc"] and kept_note:
            v = dn.group("body").strip()
            if v and _h(v) != kept_note[0] and _h(v) != _h(note):
                note = v
                conn.execute("UPDATE docs SET note = ? WHERE id = ?", (v, doc_id))
    full = own and bool(hls or note)
    blocks = []
    if m_["doc"] and (full or m_["kind"] == "torah"):
        row = conn.execute("SELECT blocks FROM doc_content WHERE id = ?", (doc_id,)).fetchone()
        try:
            blocks = json.loads(row[0]) if row and row[0] else []
        except ValueError:
            blocks = []
    doc = vaultmd.Doc(blocks, m_["kind"], m_["url"]) if full and blocks else None
    book = None
    if m_["kind"] == "torah":
        d = conn.execute("SELECT summary FROM docs WHERE id = ?", (doc_id,)).fetchone()
        mb = re.match(r"^(.*?)\s+\d", (d["summary"] if d else "") or "")
        book = mb.group(1) if mb else None
    for h in hls:
        try:
            h["p"] = json.loads(h["pos"]) if h["pos"] else {}
        except ValueError:
            h["p"] = {}
        if not isinstance(h["p"], dict):
            h["p"] = {}
        h["at"] = doc.place(h["id"], h["text"], h["p"]) if doc else None
        if h["at"] is not None and doc.blocks[h["at"]].get("t") in ("h2", "h3"):
            h["at"] = None                         # a heading has no block id to link to
    from . import jump
    hls.sort(key=lambda h: (0, *doc.start[h["id"]]) if doc and h["id"] in doc.start
             else (1, jump.order({"pos": h["p"]}) or 0, h["created"] or 0))

    parts = [START]
    if full:
        legacy = "\n## Data\n- SOURCE:" in text[:m.start() if m else len(text)]     # an older Daf's head says where it's from
        lines = []
        if not legacy:
            if m_["url"]:
                site = m_["source"] or urlparse(m_["url"]).netloc
                lines.append(f"**Source:** [{vaultmd._esc(site)}]({vaultmd._url(m_['url'])})")
            names = _authors(m_["author"], m_["category"])
            if names:
                lines.append("**Author:** " + ", ".join(f"[[{n}]]" for n in names))
            if m_["published"]:
                lines.append("**Published:** " + _date(m_["published"], settings))
        lines.append(f"**In Daf:** [Open]({m_['daf']})")
        parts += ["\n".join(lines), ""]
    if note:
        parts += ["## Notes", "", note.strip() + " ^daf-note", ""]
    if hls or not full:                     # a note with only your note on it has no Highlights heading
        parts += ["## Highlights", ""]
    for h in hls:
        p = h["p"]
        loc = _ts(p["t"]) if p.get("t") is not None else None
        bi = h["at"] if h["at"] is not None else p.get("b")
        if m_["kind"] == "torah" and isinstance(bi, int) and 0 <= bi < len(blocks) and isinstance(blocks[bi], dict) and blocks[bi].get("n"):
            loc = f"{book + ' ' if book else ''}{blocks[bi]['n']}"
        quote_ = _quote(h, loc, h["at"])
        if h["user_note"]:
            parts += [quote_, "", f"{h['user_note'].strip()} ^daf-h{_short(h['id'])}", ""]
        else:
            parts += [quote_ + f" ^daf-h{_short(h['id'])}", ""]
    if doc:
        parts += _text_sections(m_, doc)
    parts.append(END)
    region = "\n".join(parts)
    new = text[:m.start()] + region + text[m.end():] if m else text.rstrip("\n") + "\n\n" + region + "\n"
    if own:
        new = _keep_daf_link(new, m_, settings)
        if backfill and full:
            new = _fill_head(new, m_, settings)
    if new != text:
        tmp = path.with_name(f".{path.name}.daf-tmp")
        tmp.write_text(new, encoding="utf-8")
        tmp.replace(path)
    for h in hls:
        if h["user_note"]:
            conn.execute("UPDATE review_state SET vault_hash = ? WHERE hl_id = ?", (_h(h["user_note"]), h["id"]))
    if m_["doc"] and note:
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", ("vault_note:" + doc_id, _h(note)))
    return "written" if new != text else "unchanged"


def refresh(conn, settings, doc_id):
    """A document's text arrived or changed (a transcript, the whole page, a PDF read): its note, if it has one."""
    b = conn.execute("SELECT vault_path FROM books WHERE id = ?", (doc_id,)).fetchone()
    return write_article(conn, settings, doc_id) if b and b["vault_path"] else "no note"


def backfill(conn, settings, dry=None):
    """Every note Daf has written for a document or a podcast clip, rewritten the current way, and any
    document with highlights or a note that never got one (`daf vault-backfill`); a Karakeep-era one is
    linked to karakeep-sync's note for it, which stays as it is. Only Daf's region
    changes, and the frontmatter keys an older Daf didn't write are added. dry: a folder that gets a
    copy of each note as it would be (same paths); the vault stays as it is. Returns {doc id: (what
    happened, the note's path)}."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM books WHERE vault_path IS NOT NULL AND (id IN (SELECT id FROM docs) OR kind = 'podcast') "
        "UNION SELECT DISTINCT book_id FROM highlights WHERE deleted = 0 AND source IN (%s) AND book_id IN (SELECT id FROM docs) "
        "UNION SELECT id FROM docs WHERE note IS NOT NULL" % ",".join("?" * len(SOURCES)), SOURCES)]
    out, real = {}, config.VAULT
    for doc_id in ids:
        b = conn.execute("SELECT vault_path FROM books WHERE id = ?", (doc_id,)).fetchone()
        rel = b["vault_path"] if b and b["vault_path"] else None
        if rel and (real / rel).exists() and not _own((real / rel).read_text(encoding="utf-8")):
            continue                              # a Readwise note or a vault essay: its region changes with its next highlight
        if dry:
            for r in (rel, None if rel else _karakeep_note(doc_id)):
                if r and (real / r).exists():
                    (dry / r).parent.mkdir(parents=True, exist_ok=True)
                    (dry / r).write_bytes((real / r).read_bytes())
            config.VAULT = dry
        try:
            what = write_article(conn, settings, doc_id, backfill=True)
        finally:
            config.VAULT = real
        b = conn.execute("SELECT vault_path FROM books WHERE id = ?", (doc_id,)).fetchone()
        after = b["vault_path"] if b else None
        out[doc_id] = ("new" if not rel and after and what == "written" else "linked" if not rel and after else what, after)
    return out
