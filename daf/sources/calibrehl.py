"""Highlights made in Calibre's own viewer (Calibre on the Mac, or its content server), from the
annotations table in Calibre's metadata.db, which Daf only reads.

Each highlight's id comes from Calibre's own (its uuid, with the Calibre book), so a sync never
makes one twice, a change in Calibre (a note, a colour) follows it into Daf, and one removed in
Calibre goes from Daf too: Calibre keeps a removed highlight as a stub marked "removed", and a
highlight Calibre no longer has at all isn't seen again (highlights.import_all marks it deleted).
Calibre's note comes along as the highlight's note, its colour as Daf's nearest, and the chapter
from Calibre's table of contents.

Its place: Calibre keeps a CFI inside the chapter's file ("/2/4/10/1:110", starting at the
document) and the chapter's number in the book's spine. Daf's reader (foliate-js) wants the
book's CFI, "epubcfi(/6/24!/4/10,/1:110,/1:239)", so the two are joined, but only after checking,
in the file Daf's reader opens, that the chapter is the one Calibre named and that the CFI's range
holds the highlighted words. When it doesn't (the book was converted or polished since, or Daf
reads another format), the reader finds the highlight by its words, as it does the Kindle's.

Calibre's bookmarks come in too, as Daf bookmarks on the book (import_bookmarks), kept by Calibre's
key for them (its bookmarks are named, one a name), so a removed one goes and a moved one moves.

The other way (calibreannots.py) Daf writes its own reader's highlights into Calibre, each with a
uuid made from its Daf id (daf_uuid); this import skips those, so nothing comes back as a copy.
"""
import base64
import colorsys
import hashlib
import json
import logging
import posixpath
import re
import zipfile
from datetime import datetime
from urllib.parse import unquote

from .. import config
from ..db import read_only

log = logging.getLogger("daf.calibrehl")
SOURCE = "calibre"
# Calibre's built-in highlight colours → Daf's; its underlines and strike-throughs are yellow, Daf's plain highlight
BUILTIN = {"yellow": "yellow", "green": "green", "blue": "blue", "red": "pink", "purple": "purple"}


def color(style):
    """Daf's colour for a Calibre highlight style: {kind: color, type: builtin, which: yellow} or a
    custom one with its own light colour ("#rrggbb"), by its hue."""
    s = style if isinstance(style, dict) else {}
    if s.get("type") == "builtin" and s.get("kind") == "color":
        return BUILTIN.get(s.get("which"), "yellow")
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(s.get("light") or s.get("background-color") or "").strip())
    if s.get("kind") == "color" and m:
        r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
        h, _l, sat = colorsys.rgb_to_hls(r, g, b)
        deg = h * 360
        if sat < 0.15:
            return "yellow"
        return ("pink" if deg < 20 or deg >= 320 else "yellow" if deg < 70 else "green" if deg < 170
                else "blue" if deg < 260 else "purple")
    return "yellow"


def _epoch(v, fallback=None):
    try:
        return int(datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return int(fallback) if fallback else None


def hid(cid, uuid):
    return "c" + hashlib.sha1(f"calibre|{cid}|{uuid}".encode()).hexdigest()[:16]


def daf_uuid(hl_id):
    """The uuid a highlight made in Daf has in Calibre: 22 characters like Calibre's own, from its Daf id."""
    return base64.urlsafe_b64encode(hashlib.sha1(f"daf-calibre|{hl_id}".encode()).digest()[:16]).decode().rstrip("=")


def ours(conn):
    """The uuids of the highlights Daf has written into Calibre, or would: they're never imported."""
    out = {r[0] for r in conn.execute("SELECT uuid FROM calibre_pushed")}
    return out | {daf_uuid(r[0]) for r in conn.execute("SELECT id FROM highlights WHERE source = 'epub'")}


def annotations(db=None, kind="highlight"):
    """Calibre's highlights (or bookmarks): [{book, format, uuid, user, data}], the removed ones too (data["removed"])."""
    c = read_only(db or config.CALIBRE_DBS[0])
    try:
        rows = c.execute("SELECT book, format, annot_id, annot_data, timestamp, user_type, user FROM annotations WHERE annot_type = ? ORDER BY id",
                         (kind,)).fetchall()
    finally:
        c.close()
    out = []
    for book, fmt, aid, data, ts, utype, user in rows:
        try:
            d = json.loads(data)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append({"book": book, "format": (fmt or "").upper(), "uuid": d.get("uuid") or aid, "aid": aid, "data": d, "ts": ts,
                        "user": f"{utype}:{user}"})
    return out


# ---------- the place: Calibre's CFI, checked against the book's file ----------
_CFI_STEP = re.compile(r"/(\d+)(?:\[([^\]]*)\])?(?::(\d+))?")
_cache = {}                     # {(path, mtime, size): the book's spine and the chapters read so far}


def _steps(cfi):
    """"/2/4/10[id]/1:110" → [(2, None, None), (4, None, None), (10, "id", None), (1, None, 110)]."""
    cfi = str(cfi or "").strip()
    out, i = [], 0
    for m in _CFI_STEP.finditer(cfi):
        if m.start() != i:
            return None
        out.append((int(m.group(1)), m.group(2) or None, int(m.group(3)) if m.group(3) is not None else None))
        i = m.end()
    return out if out and i == len(cfi) else None


def _esc(s):
    return re.sub(r"([\^\[\](),;=])", r"^\1", s)


def _part(steps):
    return "".join(f"/{n}" + (f"[{_esc(i)}]" if i else "") + (f":{o}" if o is not None else "") for n, i, o in steps)


def book_cfi(base, start, end):
    """The book's range CFI from the spine's part and the two in-document paths (already without
    Calibre's step for the document itself), the way foliate-js writes one: the shared steps, then
    where it starts and where it ends."""
    common = []
    for a, b in zip(start, end):
        if a[0] != b[0] or a[2] is not None or b[2] is not None or a[1] != b[1]:
            break
        common.append(a)
    n = len(common)
    return f"epubcfi({base}!{_part(common)},{_part(start[n:])},{_part(end[n:])})"


def _parse_xml(raw):
    from lxml import etree
    try:
        return etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    except etree.XMLSyntaxError:
        return etree.fromstring(raw, etree.XMLParser(recover=True, resolve_entities=False, no_network=True, huge_tree=True))


def _flat(root):
    """The document's text as UTF-16 (the reader's offsets are a browser's), and where each chunk of
    text starts in it: {(element, odd index): position}. Comments and processing instructions don't
    count, as in a CFI; the text after one stays in the chunk it's in."""
    buf, pos = bytearray(), {}

    def walk(el):
        pos[(el, 1)] = len(buf) // 2
        buf.extend((el.text or "").encode("utf-16-le"))
        k = 1
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch)
                k += 2
                pos[(el, k)] = len(buf) // 2
            buf.extend((ch.tail or "").encode("utf-16-le"))
    walk(root)
    return bytes(buf), pos


def _chunks(el):
    """The element's own text, chunk by chunk: [(odd index, length in UTF-16)], the text before its
    first child element first, then the text after each child element."""
    out, k, n = [], 1, len((el.text or "").encode("utf-16-le")) // 2
    for ch in el:
        if isinstance(ch.tag, str):
            out.append((k, n))
            k, n = k + 2, 0
        n += len((ch.tail or "").encode("utf-16-le")) // 2
    out.append((k, n))
    return out


def _points(root, pos, steps):
    """Where an in-document path (from the root element's children) can land: [(position in the
    flat text, the path's last step as the CFI spec has it)]. Two at most, for an offset that falls
    between two chunks of text (before and after a child element).

    Calibre's viewer counts a text offset from the parent's first child, across all of its own text
    and skipping what's inside its child elements ("/1:288" can be well past the first chunk), where
    the spec and foliate-js count within one chunk; a last step of /1 (or /2, when the parent starts
    with an element) is read Calibre's way, any other odd one the spec's."""
    el = root
    for n, ident, _off in steps[:-1]:
        kids = [c for c in el if isinstance(c.tag, str)]
        if n % 2 or not 0 < n // 2 <= len(kids):
            return []
        el = kids[n // 2 - 1]
        if ident and el.get("id") != ident:
            return []
    n, _ident, off = steps[-1]
    chunks = _chunks(el)
    if off is None:
        if n % 2:
            return [(pos[(el, n)], (n, None, 0))] if (el, n) in pos else []
        kids = [c for c in el if isinstance(c.tag, str)]
        return [(pos[(kids[n // 2 - 1], 1)], steps[-1])] if 0 < n // 2 <= len(kids) else []
    if n % 2 and n > 1:                                  # the spec's way: within that chunk
        size = dict(chunks).get(n)
        return [(pos[(el, n)] + off, (n, None, off))] if size is not None and off <= size else []
    if n == 2 and not [c for c in el if isinstance(c.tag, str)]:
        return []
    out, left = [], off
    for i, (k, size) in enumerate(chunks):
        if left < size or (left == size and (not out)):
            out.append((pos[(el, k)] + left, (k, None, left)))
        if left == size and i + 1 < len(chunks):        # the very end of one chunk is the start of the next
            nk = chunks[i + 1][0]
            out.append((pos[(el, nk)], (nk, None, 0)))
            break
        if left < size:
            break
        left -= size
    return out[:2]


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[\u00ad\u200b-\u200d\ufeff]", "", s or "")).strip()


def _book(path):
    """The EPUB's spine: [(name in the zip, the itemref's CFI, linear, size)], read once per file version."""
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _cache:
        with zipfile.ZipFile(path) as z:
            cont = _parse_xml(z.read("META-INF/container.xml"))
            opf_name = next(e.get("full-path") for e in cont.iter() if isinstance(e.tag, str) and e.tag.endswith("rootfile"))
            pkg = _parse_xml(z.read(opf_name))
            kids = [e for e in pkg if isinstance(e.tag, str)]
            spine = next(e for e in kids if e.tag.endswith("spine"))
            manifest = next(e for e in kids if e.tag.endswith("manifest"))
            hrefs = {e.get("id"): e.get("href") for e in manifest if isinstance(e.tag, str) and e.tag.endswith("item")}
            base = posixpath.dirname(opf_name)
            sp = f"/{(kids.index(spine) + 1) * 2}" + (f"[{_esc(spine.get('id'))}]" if spine.get("id") else "")
            sizes = {i.filename: i.file_size for i in z.infolist()}
            items = []
            refs = [e for e in spine if isinstance(e.tag, str)]
            for j, ref in enumerate(refs):
                if not ref.tag.endswith("itemref"):
                    continue
                href = hrefs.get(ref.get("idref"))
                name = posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0]))) if href else None
                items.append((name, sp + f"/{(j + 1) * 2}" + (f"[{_esc(ref.get('id'))}]" if ref.get("id") else ""),
                              ref.get("linear") != "no", sizes.get(name, 0)))
        while len(_cache) >= 8:
            _cache.pop(next(iter(_cache)))
        _cache[key] = {"items": items, "docs": {}}
    return _cache[key]


def _doc(path, bk, i):
    """A chapter of the book, parsed once: (root, its text as UTF-16, where each chunk starts)."""
    if i not in bk["docs"]:
        with zipfile.ZipFile(path) as z:
            root = _parse_xml(z.read(bk["items"][i][0]))
        bk["docs"][i] = (root, *_flat(root))
    return bk["docs"][i]


def _fraction(bk, i, at, text):
    """How far into the book a place is, the way foliate-js measures it: by the chapters' sizes."""
    sizes = [sz if lin and sz > 0 else 0 for _n, _c, lin, sz in bk["items"]]
    total = sum(sizes)
    if not total or not sizes[i]:
        return None
    return round((sum(sizes[:i]) + at / max(1, len(text) // 2) * sizes[i]) / total, 6)


def place(path, a):
    """For one Calibre highlight in the EPUB at `path`: {cfi, fraction, sec} when its CFI holds its
    words in this very file, else {sec} when the chapter is there, else {}."""
    try:
        bk = _book(path)
    except Exception:  # noqa: BLE001 - not an EPUB Daf can read: the words will do
        return {}
    items, i = bk["items"], a.get("spine_index")
    if not isinstance(i, int) or not 0 <= i < len(items) or (a.get("spine_name") and items[i][0] != a.get("spine_name")):
        return {}
    out = {"sec": i}
    start, end = _steps(a.get("start_cfi")), _steps(a.get("end_cfi"))
    if not start or not end or len(start) < 2 or len(end) < 2 or start[0][0] != 2 or end[0][0] != 2:
        return out                                      # Calibre's paths begin at the document: /2 is its root element
    start, end = start[1:], end[1:]
    try:
        root, text, pos = _doc(path, bk, i)
        starts, ends = _points(root, pos, start), _points(root, pos, end)
    except Exception:  # noqa: BLE001
        return out
    want = _norm(a.get("highlighted_text")).casefold()
    for s, s_last in starts[::-1]:                       # at a chunk's edge: the start's later reading first, the end's earlier
        for e, e_last in ends:
            if e <= s or _norm(text[2 * s:2 * e].decode("utf-16-le", "replace")).casefold() != want:
                continue
            out.update(cfi=book_cfi(items[i][1], start[:-1] + [s_last], end[:-1] + [e_last]), fraction=_fraction(bk, i, s, text))
            return out
    return out


# ---------- the rows for highlights.import_all ----------
def rows(conn, settings):
    """Calibre's highlights as Daf highlight rows ({…, "color"}), on their Daf books (a Calibre book
    Daf hasn't listed yet gets its row first, as Import list does)."""
    from .. import catalog, ebooks, importlist
    anns, mine = annotations(), ours(conn)
    live = [a for a in anns if not a["data"].get("removed") and (a["data"].get("highlighted_text") or "").strip() and a["uuid"] not in mine]
    cids = sorted({a["book"] for a in live})
    if not cids:
        return []
    q = f"SELECT calibre_id, id FROM books WHERE calibre_id IN ({','.join('?' * len(cids))})"
    daf = {r[0]: r[1] for r in conn.execute(q, cids)}
    missing = [i for i in cids if i not in daf]
    if missing:
        cal = catalog.calibre_rows(settings)[0]
        new = {i: (cal[i]["title"], cal[i]["authors"]) for i in missing if i in cal}
        if new:
            importlist.add_daf_rows(conn, new, settings)
            daf.update({r[0]: r[1] for r in conn.execute(q, cids)})
    files = {}
    out = []
    for a in live:
        bid = daf.get(a["book"])
        if not bid:
            continue                                    # gone from Calibre since
        d = a["data"]
        if bid not in files:
            files[bid] = ebooks.book_file(conn, bid)
        path, fmt = files[bid]
        p = place(path, d) if path and fmt == a["format"] and fmt in ("EPUB", "KEPUB") else {}
        toc = [str(t).strip() for t in d.get("toc_family_titles") or [] if str(t).strip()] if isinstance(d.get("toc_family_titles"), list) else []
        # pos: the reader's place for it (cfi, fraction, sec), Calibre's uuid and format, and the colour Calibre gave it ("c")
        pos = {**p, "calibre": a["uuid"], "format": a["format"], "c": color(d.get("style"))}
        out.append({"id": hid(a["book"], a["uuid"]), "book_id": bid, "source": SOURCE,
                    "text": d["highlighted_text"].strip(), "note": (d.get("notes") or "").strip() or None,
                    "chapter": toc[-1][:200] if toc else None, "page": None,
                    "created": _epoch(d.get("timestamp"), a["ts"]),
                    "pos": json.dumps({k: v for k, v in pos.items() if v is not None})})
    return out


def colors_before(conn):
    """The colour Calibre gave each highlight at the last sync: {id: colour}."""
    out = {}
    for i, p in conn.execute("SELECT id, pos FROM highlights WHERE source = ?", (SOURCE,)):
        try:
            out[i] = json.loads(p).get("c") if p else None
        except ValueError:
            out[i] = None
    return out


def colors_after(conn, rows, before):
    """A new highlight takes Calibre's colour, and so does one whose colour changed in Calibre; one
    recoloured in Daf since keeps Daf's until Calibre's changes."""
    for r in rows:
        c = json.loads(r["pos"]).get("c")
        if c and (r["id"] not in before or before[r["id"]] != c):
            conn.execute("UPDATE highlights SET color = ? WHERE id = ?", (c, r["id"]))



# ---------- Calibre's bookmarks, as Daf bookmarks ----------
GONE_KEY = "calibre_bookmarks_gone"        # kv: the Calibre bookmarks taken out in Daf, so a sync doesn't put them back


def bookmark_place(path, pos):
    """A Calibre bookmark's position ("epubcfi(/24/2/4/14/1:95)": the chapter's step, then Calibre's
    path in it) → {cfi (the reader's), fraction, excerpt}; just the chapter's start when the place
    isn't in this file; {} when the chapter isn't either."""
    m = re.fullmatch(r"epubcfi\((.*)\)", str(pos or "").strip())
    steps = _steps(re.sub(r"[~@][^/\[\]]*$", "", m.group(1))) if m and "!" not in m.group(1) else None
    if not steps or len(steps) < 2 or steps[0][0] % 2 or steps[1][0] != 2:
        return {}
    try:
        bk = _book(path)
    except Exception:  # noqa: BLE001
        return {}
    i = steps[0][0] // 2 - 1
    if not 0 <= i < len(bk["items"]):
        return {}
    base, out = bk["items"][i][1], {"cfi": f"epubcfi({bk['items'][i][1]}!/4)", "fraction": _fraction(bk, i, 0, b"")}
    try:
        root, text, at = _doc(path, bk, i)
        pts = _points(root, at, steps[2:]) if len(steps) > 2 else []
    except Exception:  # noqa: BLE001
        return out
    if not pts:
        return out
    x, last = pts[-1]                                   # at a chunk's edge, the text after it
    words = _norm(text[2 * x:2 * x + 2000].decode("utf-16-le", "replace"))
    return {"cfi": f"epubcfi({base}!{_part(steps[2:-1] + [last])})", "fraction": _fraction(bk, i, x, text),
            "excerpt": (words[:140].rsplit(" ", 1)[0] if len(words) > 140 else words) or None}


def import_bookmarks(conn, settings):
    """Calibre's bookmarks on their Daf books (for books Daf reads as the format they were made in).
    Returns how many there are. One removed in Calibre goes from Daf; one taken out in Daf stays out."""
    from .. import ebooks
    anns = annotations(kind="bookmark")
    gone = set()
    r = conn.execute("SELECT v FROM kv WHERE k = ?", (GONE_KEY,)).fetchone()
    if r and r[0]:
        gone = set(json.loads(r[0]))
    daf = {row[0]: row[1] for row in conn.execute("SELECT calibre_id, id FROM books WHERE calibre_id IS NOT NULL")}
    files, keep, present = {}, [], set()
    for a in anns:
        d = a["data"]
        title = str(d.get("title") or "").strip()
        bid = daf.get(a["book"])
        if d.get("removed") or not title or not bid or d.get("pos_type", "epubcfi") != "epubcfi":
            continue
        key = f"{a['book']}|{a['format']}|{a['user']}|{title}"
        present.add(key)
        if key in gone:
            continue
        if bid not in files:
            files[bid] = ebooks.book_file(conn, bid)
        path, fmt = files[bid]
        p = bookmark_place(path, d.get("pos")) if path and fmt == a["format"] else {}
        if not p:
            continue
        mid = "m" + hashlib.sha1(f"calibre|{key}".encode()).hexdigest()[:15]
        keep.append(mid)
        conn.execute("INSERT INTO book_marks (id, book_id, cfi, fraction, chapter, excerpt, created, calibre) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                     "ON CONFLICT(id) DO UPDATE SET book_id = excluded.book_id, cfi = excluded.cfi, fraction = excluded.fraction, "
                     "chapter = excluded.chapter, excerpt = excluded.excerpt, created = excluded.created, calibre = excluded.calibre",
                     (mid, bid, p["cfi"], p.get("fraction"), title[:200], p.get("excerpt"), _epoch(d.get("timestamp"), a["ts"]), key))
    conn.execute(f"DELETE FROM book_marks WHERE calibre IS NOT NULL AND id NOT IN ({','.join('?' * len(keep))})", keep)
    if gone:
        conn.execute("UPDATE kv SET v = ? WHERE k = ?", (json.dumps(sorted(gone & present)), GONE_KEY))
    return len(keep)


def bookmark_taken_out(conn, key):
    """A Calibre bookmark taken out in Daf: remembered, so the next sync doesn't bring it back."""
    r = conn.execute("SELECT v FROM kv WHERE k = ?", (GONE_KEY,)).fetchone()
    gone = set(json.loads(r[0])) if r and r[0] else set()
    gone.add(key)
    conn.execute("INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (GONE_KEY, json.dumps(sorted(gone))))
