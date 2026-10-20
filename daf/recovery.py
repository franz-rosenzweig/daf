"""Recovery (#recovery): the Big Book divided by its chapters, the Step 10 and 11 readings, prayers,
and the other recovery books, on a page of its own in the Library.

Everything here comes from the reader's own copies in Calibre (private titles, so they stay out of
the review, Signal, the nightstand and the Kindle), and the readings and prayers open at their place
in that copy (`#ebook/<id>/q:<words>`, found by the reader's search). The only text kept here is
what is in the public domain (the Serenity Prayer, the prayer of St. Francis) and the first words of
each passage, which is how the reader finds it.

The EPUB has no printed page numbers, so the first 164 pages carry the Fourth Edition's own (the
chapters' first pages, the same in every printing); where a chapter starts in the file comes from its
place in the spine.
"""
import json
import re
import zipfile
import posixpath
import xml.etree.ElementTree as ET

from . import ebooks

BIG_BOOK = re.compile(r"alcoholics anonymous.*(big book|fourth edition)|big book.*alcoholics anonymous", re.I)
# A.A.'s own literature and books about A.A., by name: nothing chosen by a general word like
# "recovery" or "addiction", which would pull in books that belong elsewhere.
OTHER = re.compile(r"big book|alcoholics anonymous|twelve steps and twelve traditions|twelve and twelve|daily reflections|"
                   r"as bill sees it|came to believe|living sober|pass it on|dr\. bob and the good oldtimers", re.I)

# The Fourth Edition's first pages (chapter number → page; 0 is The Doctor's Opinion).
PAGES = {0: "xxv", 1: "1", 2: "17", 3: "30", 4: "44", 5: "58", 6: "72", 7: "89", 8: "104", 9: "122", 10: "136", 11: "151"}

READINGS = [
    {"id": "step10", "step": "Step 10", "title": "Continue to take personal inventory", "page": "84",
     "find": "Continue to watch for selfishness, dishonesty, resentment, and fear", "when": "day"},
    {"id": "morning", "step": "Step 11", "title": "On awakening", "page": "86",
     "find": "On awakening let us think about the twenty-four hours ahead", "when": "morning"},
    {"id": "evening", "step": "Step 11", "title": "When we retire at night", "page": "86",
     "find": "When we retire at night, we constructively review our day", "when": "evening"},
]

PRAYERS = [
    {"id": "serenity", "title": "Serenity Prayer",
     "text": "God, grant me the serenity to accept the things I cannot change, courage to change the things I can, and wisdom to know the difference."},
    {"id": "third", "title": "Third Step Prayer", "page": "63", "first": "God, I offer myself to Thee…", "find": "God, I offer myself to Thee"},
    {"id": "seventh", "title": "Seventh Step Prayer", "page": "76", "first": "My Creator, I am now willing…", "find": "My Creator, I am now willing"},
    {"id": "francis", "title": "Eleventh Step Prayer", "note": "The prayer of St. Francis",
     "text": "Lord, make me a channel of thy peace; that where there is hatred, I may bring love; that where there is wrong, "
             "I may bring the spirit of forgiveness; that where there is discord, I may bring harmony; that where there is error, "
             "I may bring truth; that where there is doubt, I may bring faith; that where there is despair, I may bring hope; "
             "that where there are shadows, I may bring light; that where there is sadness, I may bring joy. Lord, grant that I "
             "may seek rather to comfort than to be comforted; to understand, than to be understood; to love, than to be loved. "
             "For it is by self-forgetting that one finds. It is by forgiving that one is forgiven. It is by dying that one "
             "awakens to Eternal Life."},
]

_cache = {}


def _chapters(path):
    """The contents of the EPUB, in order: [{label, href, start (0..1), depth}]."""
    key = (str(path), path.stat().st_mtime)
    if key in _cache:
        return _cache[key]
    z = zipfile.ZipFile(path)
    opf_path = re.search(r'full-path="([^"]+)"', z.read("META-INF/container.xml").decode()).group(1)
    opf = ET.fromstring(z.read(opf_path))
    ns = {"o": "http://www.idpf.org/2007/opf"}
    base = posixpath.dirname(opf_path)
    items = {i.get("id"): i for i in opf.iterfind(".//o:manifest/o:item", ns)}
    spine = [posixpath.normpath(posixpath.join(base, items[r.get("idref")].get("href"))) for r in opf.iterfind(".//o:spine/o:itemref", ns)
             if r.get("idref") in items]
    sizes = [z.getinfo(p).file_size if p in z.namelist() else 0 for p in spine]
    total = sum(sizes) or 1
    starts, acc = {}, 0
    for p, s in zip(spine, sizes):
        starts[p] = acc / total
        acc += s
    ncx_id = opf.find(".//o:spine", ns).get("toc")
    ncx_path = posixpath.normpath(posixpath.join(base, items[ncx_id].get("href"))) if ncx_id in items else None
    out = []
    if ncx_path:
        ncx = ET.fromstring(z.read(ncx_path))
        nn = {"n": "http://www.daisy.org/z3986/2005/ncx/"}

        def walk(node, depth):
            for np in node.findall("n:navPoint", nn):
                label = " ".join("".join(np.find("n:navLabel/n:text", nn).itertext()).split())
                src = np.find("n:content", nn).get("src")
                file = posixpath.normpath(posixpath.join(posixpath.dirname(ncx_path), src.split("#")[0]))
                # The reader finds a section by its path in the zip (foliate's section ids), plus the anchor.
                out.append({"label": label, "href": file + ("#" + src.split("#", 1)[1] if "#" in src else ""),
                            "start": starts.get(file, 0.0), "depth": depth})
                walk(np, depth + 1)
        walk(ncx.find("n:navMap", nn), 0)
    _cache[key] = out
    return out


def _sections(toc):
    """The Big Book's contents in three parts: the first 164 pages, the stories, the appendices."""
    first, stories, appendices, part = [], [], [], None
    phase = "front"
    for t in toc:
        lab = t["label"]
        up = lab.upper()
        m = re.match(r"^(\d+)\s+(.*)$", lab)
        if "DOCTOR’S OPINION" in up or "DOCTOR'S OPINION" in up:
            phase = "first"
            first.append(dict(t, n="", title="The Doctor’s Opinion", page=PAGES[0]))
            continue
        if up.startswith("PART I") or "PERSONAL STORIES" in up:
            phase = "stories"
        if up.startswith("APPENDI") or re.match(r"^[IVX]+\s+THE A\.A\. TRADITION", up):
            phase = "appendices"
        if phase == "first" and m:
            n = int(m.group(1))
            first.append(dict(t, n=str(n), title=_title(m.group(2)), page=PAGES.get(n)))
            if n == 11:
                phase = "after"
        elif phase == "stories":
            if up.startswith("PART "):
                part = _title(re.sub(r"^PART\s+[IVX]+\s*", "", lab))
                stories.append(dict(t, n="", title=_title(lab), part=True))
            else:
                stories.append(dict(t, n=m.group(1) if m else "", title=_title(m.group(2) if m else lab), group=part))
        elif phase == "appendices" and up != "APPENDICES":
            m2 = re.match(r"^([IVX]+)\s+(.*)$", lab)
            appendices.append(dict(t, n=m2.group(1) if m2 else "", title=_title(m2.group(2) if m2 else lab)))
    return first, stories, appendices


SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def _title(s):
    """'HOW IT WORKS' → 'How It Works' (the book sets its contents in capitals)."""
    if s != s.upper():
        return s
    words = s.lower().split()
    return " ".join(w if (i and w in SMALL) else (w[:1].upper() + w[1:]) for i, w in enumerate(words)).replace("A.a.", "A.A.").replace("’S", "’s")


def page(conn, settings):
    """Everything the Recovery page shows."""
    rows = [dict(r) for r in conn.execute("SELECT id, title, author, progress, calibre_path, last_read FROM books WHERE kind = 'book'")]
    big = next((b for b in rows if BIG_BOOK.search(b["title"] or "")), None)
    others = [b for b in rows if b is not big and OTHER.search(b["title"] or "")]
    out = {"book": None, "first": [], "stories": [], "appendices": [], "readings": READINGS, "prayers": PRAYERS,
           "others": [{"id": b["id"], "title": b["title"], "author": b["author"], "progress": b["progress"], "has_cover": bool(b["calibre_path"])}
                      for b in sorted(others, key=lambda b: -(b["last_read"] or 0))],
           "highlights": []}
    if not big:
        return out
    path, fmt = ebooks.book_file(conn, big["id"])
    pos = conn.execute("SELECT fraction, chapter FROM book_positions WHERE book_id = ?", (big["id"],)).fetchone()
    frac = max((pos["fraction"] or 0) if pos else 0, (big["progress"] or 0) / 100)
    out["book"] = {"id": big["id"], "title": big["title"], "author": big["author"], "has_cover": bool(big["calibre_path"]),
                   "progress": round(frac * 100, 1), "format": fmt}
    if path and (fmt or "").lower() == "epub":
        try:
            first, stories, appendices = _sections(_chapters(path))
        except Exception:  # noqa: BLE001 - a book that won't open still shows the readings and prayers
            first, stories, appendices = [], [], []
        everything = first + stories + appendices
        for i, c in enumerate(everything):
            end = next((x["start"] for x in everything[i + 1:] if x["start"] > c["start"]), 1.0)
            c["read"] = 100 if frac >= end else 0 if frac <= c["start"] else round((frac - c["start"]) / (end - c["start"]) * 100)
        cur = next((c for c in first + stories if 0 < c["read"] < 100), None)
        out.update(first=first, stories=stories, appendices=appendices,
                   now={"title": cur["title"], "href": cur["href"], "page": cur.get("page")} if cur else None)
    out["highlights"] = [dict(r) for r in conn.execute(
        "SELECT h.id, h.text, h.created FROM highlights h WHERE h.book_id = ? AND h.deleted = 0 ORDER BY h.created DESC LIMIT 3", (big["id"],))]
    out["highlight_count"] = conn.execute("SELECT COUNT(*) FROM highlights WHERE book_id = ? AND deleted = 0", (big["id"],)).fetchone()[0]
    return out
