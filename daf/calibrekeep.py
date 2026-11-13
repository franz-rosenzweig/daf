"""What Daf keeps up to date in Calibre, a little at each sync (sync.py), through calibrewrite (so
Calibre makes the change):

- The Read column (a Calibre enumeration column, `#read` unless settings say `calibre_read_column`)
  follows each book's status in Daf (which follows Hardcover and the vault note): To read → Planning,
  Reading → Reading, Read → Finished, Paused → Paused, Dropped → Dropped, matched to the column's own
  choices by name. A book whose column is empty gets Daf's status; after that, when the status in Daf
  changes, the column follows. Where the two disagreed before Daf first looked (the column says Dropped,
  Daf says To read), nothing is changed: Check library lists them, to decide by hand. "Maybe" counts as
  agreeing with To read.
- The KOReader columns, the ones Calibre's KOReader Sync plugin fills (`#ko_progfloat` and `#ko_status`
  unless settings say `calibre_progress_column` / `calibre_status_column`): how far I am in each book,
  as Daf knows it from every place I read (the Kindle, Daf's reader…), as a fraction like the plugin's;
  and the status in KOReader's words: Reading → reading, Read → complete, Paused → abandoned (KOReader's
  On hold). To read and Dropped have no KOReader word, so the status column is left as it is for them.
- Page counts: a book with an EPUB and no count in the Pages column (`#pages`) gets one, the way Calibre's
  Count Pages plugin counts by default (about 2,170 characters a page), a few books a sync. All books →
  the chosen books' ⋯ → Count pages counts any book again.

- Calibre's built-in metadata sources (Google, Amazon…), updated once a day from calibre's own server,
  as the Calibre app does for itself (calibrefind.update_sources), so Find details asks them the way
  they work now.

Off with settings `calibre_keep: false`."""
import html
import json
import logging
import math
import re
import sqlite3
import time
import zipfile

from . import config

log = logging.getLogger("daf.calibrekeep")
CHARS_PER_PAGE = 2170
PAGES_PER_SYNC = 10
# Daf's status → words a Read column's choice starts with, in order of preference
WANT = {"to-read": ("planning", "to read", "want", "to-read", "tbr"), "reading": ("reading", "currently"),
        "read": ("finished", "read", "done"), "paused": ("paused", "on hold"), "dropped": ("dropped", "dnf", "did not finish", "abandoned")}
AGREE = {"to-read": ("maybe",)}


def _ro():
    return sqlite3.connect(f"file:{config.CALIBRE_DBS[0]}?mode=ro", uri=True)


def _column(c, label, kind):
    r = c.execute("SELECT id, datatype, display FROM custom_columns WHERE label = ?", (label.lstrip("#"),)).fetchone()
    return r if r and r[1] == kind else None


def _plain(v):
    return re.sub(r"[^a-z -]", "", (v or "").lower()).strip()


def read_choices(display):
    """{daf status: the column's choice for it}, by the choices' names."""
    try:
        values = json.loads(display or "{}").get("enum_values") or []
    except ValueError:
        values = []
    out = {}
    for status, words in WANT.items():
        for w in words:
            hit = next((v for v in values if _plain(v).startswith(w)), None)
            if hit:
                out[status] = hit
                break
    return out


def read_plan(conn, settings):
    """→ (changes {choice: [calibre ids]}, seen {cid: status}, conflicts [{id, title, calibre, daf}]) for the Read column."""
    label = settings.get("calibre_read_column") or "#read"
    c = _ro()
    try:
        col = _column(c, label, "enumeration")
        if not col:
            return {}, {}, [], None
        choices = read_choices(col[2])
        cur = dict(c.execute(f"SELECT l.book, v.value FROM books_custom_column_{col[0]}_link l JOIN custom_column_{col[0]} v ON v.id = l.value"))
        titles = dict(c.execute("SELECT id, title FROM books"))
    finally:
        c.close()
    r = conn.execute("SELECT v FROM kv WHERE k = 'calibre_read_seen'").fetchone()
    before = json.loads(r[0]) if r else {}
    changes, seen, conflicts = {}, {}, []
    for cid, status in conn.execute("SELECT calibre_id, status FROM books WHERE calibre_id IS NOT NULL AND status IS NOT NULL"):
        want = choices.get(status)
        if not want:
            continue
        seen[str(cid)] = status
        have = cur.get(cid)
        if have == want or (have and _plain(have).startswith(AGREE.get(status, ("\x00",)))):
            continue
        if not have or _plain(have) in ("", "--", "-") or (str(cid) in before and before[str(cid)] != status):
            changes.setdefault(want, []).append(cid)          # empty, or Daf's status has changed since: it follows
        else:
            conflicts.append({"id": cid, "title": titles.get(cid, ""), "calibre": have, "daf": status})
    return changes, seen, conflicts, "#" + label.lstrip("#")


def keep_read(conn, settings):
    changes, seen, _conf, key = read_plan(conn, settings)
    if not key:
        return 0
    n = 0
    if changes:
        from . import calibrewrite
        calibrewrite.run([{"op": "set", "ids": ids, "fields": {key: choice}} for choice, ids in changes.items()], timeout=300)
        n = sum(len(v) for v in changes.values())
    conn.execute("INSERT INTO kv (k, v) VALUES ('calibre_read_seen', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(seen),))
    return n


KO_STATUS = {"reading": "reading", "read": "complete", "paused": "abandoned"}


def ko_plan(conn, settings):
    """→ (ops, n) for the KOReader columns: only what differs from what Calibre has now."""
    pcol = settings.get("calibre_progress_column") or "#ko_progfloat"
    scol = settings.get("calibre_status_column") or "#ko_status"
    c = _ro()
    try:
        pc = _column(c, pcol, "float")
        sc = _column(c, scol, "text")
        have_p = dict(c.execute(f"SELECT book, value FROM custom_column_{pc[0]}")) if pc else {}
        have_s = {}
        if sc:
            try:
                have_s = dict(c.execute(f"SELECT book, value FROM custom_column_{sc[0]}"))
            except sqlite3.OperationalError:          # a text column Calibre keeps in a link table
                have_s = dict(c.execute(f"SELECT l.book, v.value FROM books_custom_column_{sc[0]}_link l JOIN custom_column_{sc[0]} v ON v.id = l.value"))
        known = {r[0] for r in c.execute("SELECT id FROM books")}
    finally:
        c.close()
    ops = []
    for cid, status, progress in conn.execute("SELECT calibre_id, status, progress FROM books WHERE calibre_id IS NOT NULL"):
        if cid not in known:
            continue
        fields = {}
        if pc and progress:
            f = round(min(100.0, max(0.0, float(progress))) / 100, 4)
            if have_p.get(cid) is None or abs(float(have_p[cid]) - f) > 0.0005:
                fields["#" + pcol.lstrip("#")] = f
        want = KO_STATUS.get(status or "")
        if sc and want and have_s.get(cid) != want:
            fields["#" + scol.lstrip("#")] = want
        if fields:
            ops.append({"op": "set", "ids": [cid], "fields": fields})
    return ops


def keep_ko(conn, settings):
    ops = ko_plan(conn, settings)
    if ops:
        from . import calibrewrite
        calibrewrite.run(ops, timeout=300)
    return len(ops)


def epub_pages(path):
    """Pages in an EPUB, as Count Pages counts them by default: its text, about 2,170 characters a page."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        m = re.search(r'full-path="([^"]+)"', z.read("META-INF/container.xml").decode("utf-8", "replace")) if "META-INF/container.xml" in names else None
        opf = m.group(1) if m else next((n for n in names if n.endswith(".opf")), None)
        if not opf:
            return None
        base = opf.rsplit("/", 1)[0] + "/" if "/" in opf else ""
        o = z.read(opf).decode("utf-8", "replace")
        items = {}
        for it in re.finditer(r"<(?:\w+:)?item\b[^>]*>", o):
            tag = it.group(0)
            i, h = re.search(r'\bid="([^"]+)"', tag), re.search(r'\bhref="([^"]+)"', tag)
            if i and h:
                items[i.group(1)] = h.group(1)
        chars = 0
        for ref in re.findall(r'<(?:\w+:)?itemref\b[^>]*\bidref="([^"]+)"', o):
            n = base + html.unescape(items.get(ref, ""))
            if n not in names:
                continue
            t = z.read(n).decode("utf-8", "replace")
            t = re.sub(r"(?is)<(head|script|style)\b.*?</\1>", " ", t)
            t = html.unescape(re.sub(r"<[^>]+>", " ", t))
            chars += len(re.sub(r"\s+", " ", t).strip())
    return max(1, math.ceil(chars / CHARS_PER_PAGE)) if chars else None


def pages_for(cids):
    """{cid: pages} for the given Calibre books' EPUBs (books without one are left out)."""
    from . import catalog
    out = {}
    for cid in cids:
        p = catalog.book_file(cid, "EPUB")
        if p and p.exists():
            try:
                n = epub_pages(p)
            except Exception:  # noqa: BLE001 - a broken EPUB is skipped
                log.warning("count pages: book %s", cid, exc_info=True)
                continue
            if n:
                out[cid] = n
    return out


def write_pages(counts):
    if counts:
        from . import calibrewrite
        calibrewrite.run([{"op": "set", "ids": [cid], "fields": {"#pages": n}} for cid, n in counts.items()], timeout=300)
    return len(counts)


def keep_pages(conn, settings):
    r = conn.execute("SELECT v FROM kv WHERE k = 'calibre_pages_skip'").fetchone()
    skip = set(json.loads(r[0])) if r else set()          # EPUBs with no text to count: not tried again
    c = _ro()
    try:
        col = _column(c, "pages", "int")
        if not col:
            return 0
        todo = [r[0] for r in c.execute(
            f"SELECT b.id FROM books b JOIN data d ON d.book = b.id AND d.format = 'EPUB' "
            f"WHERE NOT EXISTS (SELECT 1 FROM custom_column_{col[0]} p WHERE p.book = b.id AND p.value > 0) ORDER BY b.id DESC")
                if r[0] not in skip][:PAGES_PER_SYNC]
    finally:
        c.close()
    counts = pages_for(todo)
    n = write_pages(counts)          # first: calibrewrite then updates Daf's rows on a connection of its own
    skip |= {cid for cid in todo if cid not in counts}
    conn.execute("INSERT INTO kv (k, v) VALUES ('calibre_pages_skip', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(sorted(skip)),))
    conn.commit()
    return n


def run(conn, settings):
    """One sync's worth. → a short report, or ''."""
    if settings.get("calibre_keep") is False:
        return ""
    out = []
    r = conn.execute("SELECT v FROM kv WHERE k = 'calibre_sources_updated'").fetchone()
    if not r or time.time() - float(r[0]) > 86400:
        try:
            from . import calibrefind
            calibrefind.update_sources()
        except Exception:  # noqa: BLE001 - tried again tomorrow
            log.warning("calibre sources update", exc_info=True)
        conn.execute("INSERT INTO kv (k, v) VALUES ('calibre_sources_updated', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (str(time.time()),))
        conn.commit()
    n = keep_read(conn, settings)
    conn.commit()                    # what it noted, before the next change opens its own connection (calibrewrite._follow)
    if n:
        out.append(f"Read column {n}")
    k = keep_ko(conn, settings)
    if k:
        out.append(f"KOReader columns {k}")
    p = keep_pages(conn, settings)
    if p:
        out.append(f"pages {p}")
    return " · ".join(out)
