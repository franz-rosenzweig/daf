"""Highlights from the Readwise years, read from the vault.

Readwise exported each article to `Reference/clippings` as a note: frontmatter (title, url,
authors, created), then `## Highlights` with one bullet per highlight, each ending in a
`([View Highlight](https://read.readwise.io/read/<id>))` link, and a nested `- Note: …` when
there was one. Daf reads those bullets (it never writes to these notes), so the old highlights
come up in the daily review with everything else.

A highlight's id comes from its Readwise id, so it keeps its review history whichever article
it ends up on: the Library's copy of the page when Daf has one (it then opens at its spot in
the reading view), otherwise a `rw:` article of its own whose vault note is the Readwise note.
"""
import hashlib
import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from .. import config, library

FOLDER = "Reference/clippings"
LINK = re.compile(r"\s*\(\[View Highlight\]\((https?://read\.readwise\.io/read/([0-9a-zA-Z]+))\)\)")
SUB = re.compile(r"^\s+- (?:\*\*)?(note|tags)(?::\*\*|\*\*:|:)\s*(.*)$", re.I)


def _unquote(v):
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def _front(text):
    """The frontmatter as {key: value or [values]}, and the body after it."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm, key = {}, None
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), _unquote(m.group(2).strip())
            fm[key] = val if val else []
        elif key and re.match(r"^\s+-\s+", line) and isinstance(fm.get(key), list):
            fm[key].append(_unquote(re.sub(r"^\s+-\s+", "", line).strip()).strip("[]"))
    return fm, text[end + 4:]


def _plain(s):
    """Readwise's markdown as text: links to their words, no emphasis marks."""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\*\*|__|==", "", s)
    return s.strip()


def _starts(lines, i):
    """Whether line i begins a highlight: a bullet, or the first line after a blank, a heading or a tag line."""
    if lines[i].startswith("- "):
        return True
    prev = lines[i - 1] if i else ""
    return not prev.strip() or prev.lstrip("- ").startswith("#")


def parse(text):
    """(frontmatter, [{rid, text, note, tags}]) for one Readwise note.

    Each View Highlight link ends a highlight, which starts at the nearest bullet, blank line or
    heading before it: the notes are written as bullets, as an outline ("- ## Highlights") or as
    plain paragraphs, and a highlight's later paragraphs may or may not be indented. A note or
    tags are the indented "- Note:" / "- Tags:" lines right after the link."""
    fm, body = _front(text)
    out, last = [], 0
    for m in LINK.finditer(body):
        lines = body[last:m.start()].split("\n")
        first = max([k for k in range(len(lines)) if _starts(lines, k)] or [0])
        para = [ln.strip() for ln in lines[first:]]
        if para and para[0].startswith("- "):
            para[0] = para[0][2:]
        note, tags, sub = [], [], None
        for ln in body[m.end():].split("\n")[1:]:
            if not ln.strip() or not ln[0].isspace():
                break
            sm = SUB.match(ln)
            if sm:
                sub = sm.group(1).lower()
                (note if sub == "note" else tags).append(sm.group(2))
            elif sub == "note":
                note.append(ln.strip())
        tl = []
        for t in tags:
            tl += [a or b for a, b in re.findall(r"\[\[([^\]]+)\]\]|#([\w/-]+)", t)]
        txt = _plain("\n".join(x for x in para if x))
        if txt:
            out.append({"rid": m.group(2), "text": txt, "note": _plain("\n".join(note)) or None, "tags": tl})
        last = m.end()
    return fm, out


def _norm(url):
    try:
        p = urlsplit((url or "").strip())
    except ValueError:
        return ""
    q = "&".join(x for x in p.query.split("&") if x and not x.lower().startswith("utm_"))
    return urlunsplit((p.scheme.lower(), (p.hostname or "").lower(), p.path.rstrip("/"), q, ""))


def rows(conn, settings, tz):
    """The Readwise highlights in the vault, as highlight rows. Makes the article rows they need."""
    folder = config.VAULT / FOLDER
    if not folder.is_dir():
        return []
    by_url = {}
    for r in conn.execute("SELECT id, url, where_ FROM docs WHERE url IS NOT NULL"):
        n = _norm(r["url"])
        if n and (n not in by_url or r["where_"] == "library"):
            by_url[n] = r["id"]
    out = []
    for path in sorted(folder.glob("*.md")):
        if ".sync-conflict-" in path.name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "read.readwise.io/read/" not in text:
            continue
        fm, hls = parse(text)
        if not hls:
            continue
        rel = str(path.relative_to(config.VAULT))
        title = (fm.get("title") if isinstance(fm.get("title"), str) else None) or path.stem
        authors = fm.get("authors") if isinstance(fm.get("authors"), list) else [fm.get("authors")] if fm.get("authors") else []
        author = ", ".join(a for a in authors if a) or None
        url = fm.get("url") if isinstance(fm.get("url"), str) else None
        try:
            created = int(datetime.strptime(str(fm.get("created"))[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=tz).timestamp())
        except ValueError:
            created = int(path.stat().st_mtime)
        bid = by_url.get(_norm(url)) if url else None
        private = 1 if library.is_private(f"{title} {author or ''}", settings) else 0
        if bid:
            d = conn.execute("SELECT * FROM docs WHERE id = ?", (bid,)).fetchone()
            from .. import reader
            reader._ensure_book(conn, d)
            # One note per article: Daf's own highlights on it later go into the Readwise note too.
            conn.execute("UPDATE books SET vault_path = COALESCE(vault_path, ?) WHERE id = ?", (rel, bid))
        else:
            bid = "rw:" + hashlib.sha1((url or rel).encode()).hexdigest()[:12]
            conn.execute("INSERT INTO books (id, kind, title, author, url, vault_path, private) VALUES (?, 'article', ?, ?, ?, ?, ?) "
                         "ON CONFLICT(id) DO UPDATE SET title = excluded.title, author = excluded.author, url = excluded.url, "
                         "vault_path = excluded.vault_path, private = excluded.private", (bid, title, author, url, rel, private))
        for i, h in enumerate(hls):
            out.append({"id": "rw" + h["rid"].lower()[:24], "book_id": bid, "source": "readwise", "text": h["text"], "note": h["note"],
                        "chapter": None, "page": None, "created": created + i, "pos": None, "tags": h["tags"]})
    return out
