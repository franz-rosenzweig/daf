"""Where a book and its audiobook meet: a place in the EPUB ↔ a second in the audiobook.

Daf knows which audiobook is which book (library.py's book_keys); this finds, for a place in one,
the same place in the other, so opening the book can offer the audiobook's place and "Listen from
here" starts the audiobook at the page.

1. The map (anchors): places known to be the same in both, with a straight line between them. To
   start with, the body of the book (without its front matter, notes and index) is the whole
   recording, and chapter titles that share words with the audiobook's are the same place. Tried on
   seven real pairs (21 places), that alone landed within six minutes, half of them within a minute
   and a half (one notes-heavy book was thirteen minutes off near its end). Pairing by the
   audiobook's chapter numbers, or by chapter lengths, was worse, 15 to 90 minutes off: an audiobook
   numbers its own marks (a prologue or the credits as its "Chapter 1", a chapter split in two).
2. Then heard (exact): about 24 seconds of the audiobook are transcribed (faster-whisper's base.en,
   five to ten seconds' work on this server) and the words are found in the book, anywhere in it
   (_find_words: three-word runs that agree on one offset). Going from the audiobook to the book,
   that is the place, to a sentence or so. Going from the book to the audiobook, the guess is heard,
   corrected by how far its words are from the page, and heard once more if it was far: within a few
   seconds. Every place found this way is kept for the book (kv "audiomap:<book>") as an anchor, so
   the map is surer there from then on.
   When what's heard isn't in this text (another translation, music, credits), the map's guess stands.

A place in the book is a character in its text: the linear spine sections' text, one after another.
From the reader it comes as the words on the page (found in the book), else its CFI (resolved in the
section's XHTML), else its fraction (foliate's, which goes by the sections' sizes in the EPUB).
Going the other way, the reader is sent words to find (book.js's C.BookPlace.go), and a fraction
should they not be found.
"""
import array
import functools
import logging
import posixpath
import re
import threading
import time
import urllib.parse
import zipfile

from lxml import etree, html as lhtml

log = logging.getLogger("daf.audiomap")
OPS = "http://www.idpf.org/2007/ops"
WORD = re.compile(r"[\w’']+", re.U)


# ---- the EPUB: sections, their text, and its contents -------------------------------------------

def _xml(data):
    return etree.fromstring(data, etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True))


def _section(data):
    """A section's body text, with where each element and each text run between them starts in it:
    {"text", "ids": {id: start}, "el": {element: start}, "runs": {element: [start of its text, of each
    child's tail…]}, "root"}. The book keeps only the text and the ids (_book); a CFI reads it again."""
    try:
        root = _xml(data)
        if root is None:
            raise ValueError
    except (etree.XMLSyntaxError, ValueError):
        root = lhtml.fromstring(data)
    body = next((e for e in root.iter() if isinstance(e.tag, str) and etree.QName(e).localname == "body"), root)
    parts, n, at, runs = [], 0, {}, {}

    def put(s):
        nonlocal n
        if s:
            parts.append(s)
            n += len(s)

    def walk(el):
        at[el] = n
        mine = [n]
        skip = isinstance(el.tag, str) and etree.QName(el).localname in ("script", "style")
        if not skip:
            put(el.text)
        for ch in el:
            if isinstance(ch.tag, str):
                walk(ch)
            mine.append(n)
            put(ch.tail)
        runs[el] = mine
        if isinstance(el.tag, str) and etree.QName(el).localname in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "blockquote", "tr"):
            put(" ")                                   # a block ends a word, as on the page

    walk(body)
    ids = {e.get("id"): p for e, p in at.items() if isinstance(e.tag, str) and e.get("id")}
    return {"root": root, "text": "".join(parts), "ids": ids, "el": at, "runs": runs}


@functools.lru_cache(maxsize=2)
def _book(path, mtime):
    """The EPUB, read once: sections (href, size, linear, text), the stream's starts, and the contents."""
    z = zipfile.ZipFile(path)
    names = {i.filename: i for i in z.infolist()}
    cont = _xml(z.read("META-INF/container.xml"))
    opf_path = next(e.get("full-path") for e in cont.iter() if isinstance(e.tag, str) and etree.QName(e).localname == "rootfile")
    opf = _xml(z.read(opf_path))
    base = posixpath.dirname(opf_path)
    full = lambda href, rel=base: posixpath.normpath(posixpath.join(rel, urllib.parse.unquote(href))).lstrip("/")
    man = {}
    for it in opf.iter("{*}item"):
        man[it.get("id")] = {"href": full(it.get("href") or ""), "type": it.get("media-type") or "", "props": it.get("properties") or ""}
    spine_el = next(opf.iter("{*}spine"))
    secs = []
    for ir in spine_el.iter("{*}itemref"):
        m = man.get(ir.get("idref"))
        if not m:
            continue
        linear = (ir.get("linear") or "yes") != "no"
        info = names.get(m["href"])
        secs.append({"href": m["href"], "size": info.file_size if info and linear else 0, "linear": linear, "text": "", "ids": {}})
    # The text of every linear section, one after another (the "stream" a place is a character in).
    start = 0
    for s in secs:
        s["start"] = start
        if s["linear"] and s["href"] in names:
            d = _section(z.read(s["href"]))
            s["text"], s["ids"] = d["text"], d["ids"]
        s["len"] = len(s["text"])
        start += s["len"]
    by_href = {s["href"]: i for i, s in enumerate(secs)}
    toc = _toc(z, man, spine_el, full)
    entries = []
    for label, href, depth in toc:
        file, _, frag = href.partition("#")
        i = by_href.get(file)
        if i is None or not secs[i]["linear"] or not label.strip():
            continue
        off = secs[i]["ids"].get(frag, 0) if frag else 0
        entries.append({"title": re.sub(r"\s+", " ", label).strip(), "pos": secs[i]["start"] + off, "depth": depth})
    entries.sort(key=lambda e: e["pos"])
    text = "".join(s["text"] for s in secs)
    for s in secs:
        s["text"] = None                              # the book's text is kept once, whole
    # Its words, lower-cased, and where each starts (two lists, not pairs: a long book has half a million).
    words, starts = [], array.array("l")
    for m in WORD.finditer(text):
        words.append(m.group(0).lower().replace("’", "'"))
        starts.append(m.start())
    return {"path": path, "secs": secs, "toc": entries, "text": text, "total": start, "words": words, "starts": starts,
            "sizes": sum(s["size"] for s in secs)}


def _toc(z, man, spine_el, full):
    """[(label, href, depth)] from the EPUB 3 nav, else the NCX."""
    nav = next((m for m in man.values() if "nav" in m["props"].split()), None)
    out = []
    if nav:
        try:
            root = _xml(z.read(nav["href"]))
            navs = [e for e in root.iter("{*}nav")]
            toc = next((e for e in navs if (e.get(f"{{{OPS}}}type") or "").split()[:1] == ["toc"] or "toc" in (e.get(f"{{{OPS}}}type") or "")), navs[0] if navs else None)
            if toc is not None:
                rel = posixpath.dirname(nav["href"])
                for a in toc.iter("{*}a"):
                    if a.get("href"):
                        depth = sum(1 for p in a.iterancestors() if isinstance(p.tag, str) and etree.QName(p).localname == "ol") - 1
                        out.append(("".join(a.itertext()), full(a.get("href"), rel), max(0, depth)))
        except (KeyError, etree.XMLSyntaxError):
            out = []
    if out:
        return out
    ncx = man.get(spine_el.get("toc") or "") or next((m for m in man.values() if m["type"] == "application/x-dtbncx+xml"), None)
    if not ncx:
        return []
    try:
        root = _xml(z.read(ncx["href"]))
    except KeyError:
        return []
    rel = posixpath.dirname(ncx["href"])
    for np in root.iter("{*}navPoint"):
        label = " ".join("".join(t.itertext()) for t in np.iterchildren("{*}navLabel"))
        c = next(np.iterchildren("{*}content"), None)
        if c is not None and c.get("src"):
            depth = sum(1 for p in np.iterancestors("{*}navPoint"))
            out.append((label, full(c.get("src"), rel), depth))
    return out


def book(path):
    p = str(path)
    import os
    return _book(p, os.stat(p).st_mtime_ns)


# ---- a place in the reader → a character in the text ------------------------------------------

def _cfi_steps(cfi):
    m = re.match(r"epubcfi\((.*)\)$", cfi or "")
    if not m:
        return None
    body = m.group(1)
    if "," in body:                                    # a range: its parent and its start
        parent, start = body.split(",")[:2]
        body = parent + start
    steps = []
    for s in body.split("/")[1:]:
        s = re.sub(r"\[[^\]]*\]", "", s)
        ind = s.endswith("!")
        s = s.rstrip("!")
        num, _, off = s.partition(":")
        if not num.isdigit():
            return None
        steps.append((int(num), int(off) if off.isdigit() else None, ind))
    return steps


def _from_cfi(B, cfi):
    """A CFI's character: its spine step picks the section, the rest walks the section's elements."""
    steps = _cfi_steps(cfi)
    if not steps or len(steps) < 2:
        return None
    i = steps[1][0] // 2 - 1
    if not 0 <= i < len(B["secs"]) or not B["secs"][i]["len"]:
        return None
    s = B["secs"][i]
    with zipfile.ZipFile(B["path"]) as z:
        doc = _section(z.read(s["href"]))
    el = doc["root"]
    pos = None
    for num, off, _ in steps[2:]:
        kids = [k for k in el if isinstance(k.tag, str)]
        if num % 2 == 0:
            if num // 2 - 1 >= len(kids):
                break
            el = kids[num // 2 - 1]
            pos = doc["el"].get(el)
            if off is not None and pos is not None:
                pos += off
        else:
            runs = doc["runs"].get(el)
            j = (num - 1) // 2
            if runs and j < len(runs):
                pos = runs[j] + (off or 0)
            break
    if pos is None:
        pos = doc["el"].get(el, 0)
    return s["start"] + min(max(0, pos), s["len"])


def _from_fraction(B, f):
    """foliate's fraction (by the sections' sizes) → a character: its section, then as far into its text."""
    total = B["sizes"] or 1
    want, before = f * total, 0
    for s in B["secs"]:
        if s["size"] and before + s["size"] >= want:
            return s["start"] + int((want - before) / s["size"] * s["len"])
        before += s["size"]
    return B["total"]


def _norm_words(text):
    return [w.lower().replace("’", "'") for w in WORD.findall(text or "")]


def _find_words(B, text, near=None, span=None):
    """Where a run of words (the page's, or what was heard) is in the book: [(its word i, the book's
    word j)], from three-word runs that agree on one offset, give or take two words (whisper drops
    and adds a few). Looks only within `span` characters of `near` when given."""
    import bisect
    want = _norm_words(text)
    if len(want) < 3:
        return []
    W, starts = B["words"], B["starts"]
    lo, hi = 0, len(W)
    if near is not None and span:
        lo = max(0, bisect.bisect_left(starts, near - span))
        hi = min(len(W), bisect.bisect_left(starts, near + span))
    need = {(want[i], want[i + 1], want[i + 2]) for i in range(len(want) - 2)}
    grams = {}
    for j in range(lo, hi - 2):
        g = (W[j], W[j + 1], W[j + 2])
        if g in need:
            grams.setdefault(g, []).append(j)
    votes = {}
    for i in range(len(want) - 2):
        for j in grams.get((want[i], want[i + 1], want[i + 2]), ()):
            votes.setdefault(j - i, []).append((i, j))
    if not votes:
        return []
    score = lambda d: sum(len(votes.get(d + k, ())) for k in range(-2, 3))
    best = max(votes, key=lambda d: (score(d), len(votes[d])))
    pairs = sorted(p for k in range(-2, 3) for p in votes.get(best + k, ()))
    return pairs if len(pairs) >= 2 else []


def char_of(B, place):
    """The character a reader's place is at: its words, else its CFI, else its fraction."""
    guess = None
    if place.get("cfi"):
        guess = _from_cfi(B, place["cfi"])
    if guess is None and place.get("fraction") is not None:
        guess = _from_fraction(B, float(place["fraction"]))
    if place.get("text"):
        f = (_find_words(B, place["text"][:600], near=guess, span=40000) if guess is not None else []) or _find_words(B, place["text"][:600])
        if f:
            i, j = f[0]
            return B["starts"][max(0, j - i)]         # where the page's first word is
    return guess if guess is not None else 0


def fraction_of(B, c):
    """A character → foliate's fraction (by the sections' sizes), for the reader to go to."""
    total = B["sizes"] or 1
    before = 0
    for s in B["secs"]:
        if s["len"] and s["start"] <= c < s["start"] + s["len"]:
            return min(1.0, (before + (c - s["start"]) / s["len"] * s["size"]) / total)
        before += s["size"]
    return 1.0


def chapter_at(B, c):
    t = None
    for e in B["toc"]:
        if e["pos"] <= c:
            t = e["title"]
        else:
            break
    return t


def snippet(B, c, n=12):
    """About n words of the text from the word at c: what the reader looks for."""
    import bisect
    W, starts = B["words"], B["starts"]
    j = max(0, bisect.bisect_right(starts, c) - 1)
    if j + n > len(W):
        j = max(0, len(W) - n)
    if not W:
        return ""
    k = min(len(W) - 1, j + n - 1)
    a, end = starts[j], starts[k] + len(W[k])
    return re.sub(r"\s+", " ", B["text"][a:end]).strip()


# ---- the map: anchors where the two are known to meet ------------------------------------------
# An audiobook's chapter marks are often only "Chapter 1", "Track 03" or "2", numbered from its own
# start (an opening credit or a prologue as its "Chapter 1", a chapter split in two), so a number in a
# title says little. Tried on real pairs, pairing by those numbers, or by the chapters' lengths, put
# the place 15 to 90 minutes off. What holds:
# - the body of the book (without its front matter, notes, index…) is the whole recording;
# - titles that share words ("Epilogue", "Part 2, Chapter 3") are the same place;
# - and best, a place found by its words (heard, below), kept for the book (kv "audiomap:<book>"), so the
#   map gets closer every time the two are matched.
# Between anchors, a place is as far into the audio as into the text.

NUMS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                                    "sixteen seventeen eighteen nineteen twenty".split())}
NUMS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90})
ORD = {w: i + 1 for i, w in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth".split())}
ROMAN = re.compile(r"^(?=[mdclxvi]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$")
DROP = {"chapter", "ch", "the", "a", "an", "of", "and", "track", "unabridged"}
FRONT = re.compile(r"^(cover|title( page)?|half title|copyright( page)?|(table of )?contents|dedication|epigraph|also by|praise for|"
                   r"about the (author|publisher)|maps?|frontispiece|by the same author|books by)\b", re.I)
BACK = re.compile(r"^(notes|endnotes|end ?notes|notes and sources|sources|acknowledge?ments|index|bibliography|selected bibliography|"
                  r"references|further reading|about the author|about the publisher|also by|copyright|credits|permissions|"
                  r"reading group guide|discussion questions|a note on the type|glossary|works cited|photo(graph)? credits)\b", re.I)


def _roman(s):
    v = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    n = 0
    for a, b in zip(s, s[1:] + " "):
        n += -v[a] if b != " " and v.get(b, 0) > v[a] else v[a]
    return n


def _title_key(t):
    """A chapter title as words to compare: numbers as numbers ("Chapter Seven", "VII", "07." → "7")."""
    t = (t or "").lower().replace("’", "'")
    t = re.sub(r"(\w+)-(\w+)", lambda m: str(NUMS[m.group(1)] + NUMS[m.group(2)]) if m.group(1) in NUMS and m.group(2) in NUMS else m.group(0), t)
    raw, toks = re.findall(r"[a-z0-9']+", t), []
    for k, w in enumerate(raw):
        if w.isdigit():
            w = str(int(w))
        elif w in NUMS:
            w = str(NUMS[w])
        elif w in ORD:
            w = str(ORD[w])
        elif ROMAN.match(w) and (len(raw) == 1 or (k and raw[k - 1] in ("chapter", "part", "book", "ch"))):
            w = str(_roman(w))                        # "VII", "Part IV"; not the "I" of "I Am"
        toks.append(w)
    return [w for w in toks if w not in DROP]


def _like(a, b):
    """How alike two chapter titles are, 0 to 1, counting only titles that share a word: numbers that
    differ are different places, and a number alone says too little. "01 - Part 1 Chapter 1" is also
    tried without its first number, which is often only the track's."""
    def keys(t):
        k = _title_key(t)
        return [k, k[1:]] if len(k) > 1 and k[0].isdigit() else [k]
    best = 0.0
    for ka in keys(a):
        for kb in keys(b):
            sa, sb = {w for w in ka if not w.isdigit()}, {w for w in kb if not w.isdigit()}
            if not sa or not sb or not sa & sb:
                continue
            na, nb = [w for w in ka if w.isdigit()], [w for w in kb if w.isdigit()]
            if (na or nb) and na != nb:
                continue
            best = max(best, 1.0 if ka == kb else len(sa & sb) / len(sa | sb))
    return best


def _align(titles, names):
    """The likest titles paired, in order on both sides: [(i, j)]."""
    n, m = len(titles), len(names)
    sim = [[max(_like(titles[i][0], names[j]), _like(titles[i][1], names[j])) for j in range(m)] for i in range(n)]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            v = sim[i - 1][j - 1]
            dp[i][j] = max(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1] + v if v >= 0.6 else 0)
    pairs, i, j = [], n, m
    while i and j:
        v = sim[i - 1][j - 1]
        if v >= 0.6 and abs(dp[i][j] - (dp[i - 1][j - 1] + v)) < 1e-9:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def body(B):
    """(start, end) of the book's own text: after its front matter, before its notes and index."""
    toc, total = B["toc"], B["total"]
    start = 0
    for e in toc:
        if e["pos"] > total * 0.2 or not FRONT.match(e["title"].strip()):
            start = e["pos"] if FRONT.match((chapter_at(B, e["pos"] - 1) or "").strip()) else start
            break
        start = next((x["pos"] for x in toc if x["pos"] > e["pos"]), start)
    end = next((e["pos"] for e in toc if e["pos"] > max(start, total * 0.5) and BACK.match(e["title"].strip())), total)
    return start, max(end, start + 1)


def anchors(B, chapters, duration, learned=()):
    """The places the book and the audiobook are known to meet, [(character, second)], in order on both
    sides, and how the strongest was found: "words" (heard and found), "chapters" (titles) or "whole"."""
    start, end = body(B)
    by_pos = {}
    for e in B["toc"]:
        by_pos.setdefault(e["pos"], []).append(e)
    pos = sorted(by_pos)
    titles, above = [], {}
    for p in pos:                                     # each place's own title, and with the one above it
        es = by_pos[p]
        for e in es:
            above[e["depth"]] = e["title"]
        own = es[-1]
        titles.append((own["title"], (above.get(own["depth"] - 1, "") + " " + own["title"]).strip() if own["depth"] else own["title"]))
    chs = sorted([c for c in chapters if c.get("start") is not None], key=lambda c: c["start"])
    named = [(pos[i], float(chs[j]["start"])) for i, j in _align(titles, [c.get("title") or "" for c in chs])]
    pts = [(c, t, 2) for c, t in learned] + [(c, t, 1) for c, t in named] + [(start, 0.0, 0), (end, float(duration or 0), 0)]
    # The surest first; one that would put the two out of order is left out.
    keep = []
    for c, t, w in sorted(pts, key=lambda p: -p[2]):
        if all((c - c2) * (t - t2) > 0 for c2, t2, _ in keep):
            keep.append((c, t, w))
    keep.sort()
    how = "words" if any(w == 2 for *_, w in keep) else "chapters" if any(w == 1 for *_, w in keep) else "whole"
    return [(c, t) for c, t, _ in keep], how


def to_time(A, c):
    """A character → a second: between the anchors on either side, as far into one as into the other."""
    if c <= A[0][0]:
        return A[0][1]
    for (c0, t0), (c1, t1) in zip(A, A[1:]):
        if c <= c1:
            return t0 + (c - c0) / max(1, c1 - c0) * (t1 - t0)
    return A[-1][1]


def to_char(A, t):
    if t <= A[0][1]:
        return A[0][0]
    for (c0, t0), (c1, t1) in zip(A, A[1:]):
        if t <= t1:
            return int(c0 + (t - t0) / max(1e-3, t1 - t0) * (c1 - c0))
    return A[-1][0]


def pace(A, c):
    """Characters a second, around character c."""
    for (c0, t0), (c1, t1) in zip(A, A[1:]):
        if c0 <= c <= c1 and t1 - t0 > 60:
            return (c1 - c0) / (t1 - t0)
    return max(1, A[-1][0] - A[0][0]) / max(1.0, A[-1][1] - A[0][1])


# ---- step 3: what's said there, found in the text --------------------------------------------

_heard, _hearing, _heard_lock = {}, {}, threading.Lock()
WINDOW = 24


def _hear(item_id, t):
    """About WINDOW seconds of the audiobook from t, transcribed: [(second, word)]. Kept a while; asked
    twice at once (the book page getting ready, then the tap), it's heard once."""
    k = (item_id, int(t))
    with _heard_lock:
        lock = _hearing.setdefault(k, threading.Lock())
    with lock:
        with _heard_lock:
            if k in _heard and time.time() - _heard[k][0] < 3600:
                return _heard[k][1]
        out = _listen(item_id, t)
        with _heard_lock:
            _heard[k] = (time.time(), out)
            _hearing.pop(k, None)
            if len(_heard) > 300:
                _heard.clear()
        return out


def _listen(item_id, t):
    from . import absapi, media
    path, local, _ = absapi.file_at(item_id, t)
    res = media.whisper(path, start=max(0.0, local), duration=WINDOW, model="base.en", timeout=180)
    out = []
    for s in res.get("segments") or []:
        ws = _norm_words(s.get("text"))
        if not ws:
            continue
        a, b = float(s["start"]), float(s.get("end") or s["start"])
        for i, w in enumerate(ws):                      # a word's time: its place in its segment
            out.append(((t - local) + a + (b - a) * i / len(ws), w))
    return out


def _found(B, item_id, t):
    """What's said from second t, found in the book: [(second, character)], or [] when too little of it
    is in this text (another translation, say, or music)."""
    heard = _hear(item_id, max(0.0, t))
    if len(heard) < 6:
        return []
    pairs = _find_words(B, " ".join(w for _, w in heard))
    if len({i for i, _ in pairs}) < 3:
        return []
    return [(heard[i][0], B["starts"][j]) for i, j in pairs]


# ---- the two directions -------------------------------------------------------------------------

def _key(book_id):
    return "audiomap:" + book_id


def _learned(conn, book_id, B):
    import json
    r = conn.execute("SELECT v FROM kv WHERE k = ?", (_key(book_id),)).fetchone()
    try:
        d = json.loads(r[0]) if r else {}
    except ValueError:
        d = {}
    return [tuple(x) for x in d.get("at", [])] if d.get("text") == B["total"] else []


def _learn(book_id, B, c, t):
    """Keep a place found by its words: the map is surer there from now on. On a connection of its
    own, written at once: the request's would hold the database's write lock through the next
    whisper, and a page turn saved meanwhile would find it locked."""
    import json
    from . import db
    with db.session() as conn:
        have = [x for x in _learned(conn, book_id, B) if abs(x[1] - t) > 120 and (x[0] - c) * (x[1] - t) > 0]
        have = sorted(have + [(int(c), round(float(t), 1))])[-200:]
        conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (_key(book_id), json.dumps({"text": B["total"], "at": have})))


def _setup(conn, book_id):
    from . import absapi, ebooks
    item_id = absapi.for_book(conn, book_id)
    if not item_id:
        return None
    path, fmt = ebooks.book_file(conn, book_id)
    if not path or fmt not in ("EPUB", "KEPUB"):
        return {"item": item_id}
    med = absapi.item(item_id).get("media") or {}
    B = book(path)
    chs = [{"start": c.get("start"), "end": c.get("end"), "title": c.get("title") or ""} for c in med.get("chapters") or []]
    dur = med.get("duration") or 0
    A, how = anchors(B, chs, dur, _learned(conn, book_id, B))
    return {"item": item_id, "B": B, "A": A, "how": how, "duration": dur, "chapters": chs}


def audio_chapter(chs, t):
    c = None
    for x in chs:
        if (x.get("start") or 0) <= t + 0.5:
            c = x.get("title")
    return c


def from_book(conn, book_id, place, exact=False):
    """A place in the book → where to start the audiobook: {t, chapter, how}. exact: hear the audiobook
    at the guess, find those words, and correct by how far they are from the place; twice at most."""
    S = _setup(conn, book_id)
    if not S or "B" not in S:
        return None
    B, A = S["B"], S["A"]
    c = char_of(B, place)
    t, how = to_time(A, c), S["how"]
    if exact and S["duration"]:
        try:
            for _ in range(2):
                got = _found(B, S["item"], max(0.0, t - WINDOW / 2))
                if not got:
                    break
                tt, cc = min(got, key=lambda x: abs(x[1] - c))
                _learn(book_id, B, cc, tt)
                t, how = tt + (c - cc) / pace(A, c), "words"
                if abs(c - cc) < 400:                 # within a sentence or two of the place
                    break
        except Exception as e:  # noqa: BLE001 - the map's guess stands
            log.info("from_book %s: %s", book_id, e)
    t = max(0.0, min(t, (S["duration"] or t) - 1))
    return {"t": round(t, 1), "chapter": chapter_at(B, c), "how": how, "audio_chapter": audio_chapter(S["chapters"], t)}


def to_book(conn, book_id, t, exact=False):
    """A second in the audiobook → the place in the book: {words, fraction, chapter, how}. exact: hear
    the 20 seconds before it and find them in the book."""
    S = _setup(conn, book_id)
    if not S or "B" not in S:
        return None
    B, A = S["B"], S["A"]
    c, how = to_char(A, t), S["how"]
    if exact and S["duration"]:
        try:
            got = _found(B, S["item"], max(0.0, t - WINDOW + 4))
            if got:
                tt, cc = min(got, key=lambda x: abs(x[0] - t))
                _learn(book_id, B, cc, tt)
                c, how = int(cc + (t - tt) * pace(A, cc)), "words"
        except Exception as e:  # noqa: BLE001
            log.info("to_book %s: %s", book_id, e)
    c = max(0, min(c, B["total"] - 1))
    return {"words": snippet(B, c), "fraction": round(fraction_of(B, c), 5), "chapter": chapter_at(B, c), "how": how}
