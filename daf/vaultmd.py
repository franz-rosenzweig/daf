"""A document's text as Markdown, for its note in the vault (vaultnotes.write_article).

Headings, paragraphs, lists, quotes, links and pictures (by their address on the web), PDF page
marks, transcripts with their times (a YouTube time opens the video there), Torah verses in
Hebrew and English. Highlighted words are marked ==like this==, and each highlighted block ends
with a block id (`^daf-b<block>`) that the note's Highlights link to.

A highlight is placed by its block and offsets when they still fit the text, otherwise by its
words, the way the reading view finds the browser extension's and the imports' highlights.
Offsets are counted without whitespace, because the reader counts over the page's text and the
Kindle over the block's plain text, which space things differently.
"""
import html
import re
import unicodedata
from html.parser import HTMLParser

FULL_TEXT_MAX = 150_000          # characters of Markdown; past that, only the highlighted blocks

# X's login wall, which Karakeep saves along with the tweets (web/reader.js XJUNK).
XJUNK = re.compile(r"^(Don’t miss what’s happening|Don't miss what's happening|People on X are the first to know\.?|Log in|Sign up|"
                   r"Trending now|Post|Conversation|Relevant people|What’s happening|New to X\?|Sign up now to get your own "
                   r"personalized timeline!|Terms of Service|Privacy Policy|Cookie Policy|Show more|@\w+)$", re.I)

_BOLD, _ITAL, _CODE, _STRIKE = 1, 2, 4, 8


class _Inline(HTMLParser):
    """Inline HTML (content.py's safe subset) → [(char, (format bits, href))]."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack = [], []

    def _state(self):
        bits, href = 0, None
        for tag, v in self.stack:
            if tag == "a":
                href = v
            else:
                bits |= v
        return bits, href

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append(("\n", self._state()))
            return
        a = dict(attrs)
        if tag == "a":
            href = a.get("href") or ""
            self.stack.append(("a", href if href.startswith(("http://", "https://")) else None))
        elif tag in ("strong", "b", "em", "i", "code", "s", "del", "strike"):
            self.stack.append((tag, {"strong": _BOLD, "b": _BOLD, "em": _ITAL, "i": _ITAL, "code": _CODE}.get(tag, _STRIKE)))

    def handle_endtag(self, tag):
        for j in range(len(self.stack) - 1, -1, -1):
            if self.stack[j][0] == tag or (tag in ("b", "strong") and self.stack[j][0] in ("b", "strong")) or \
                    (tag in ("i", "em") and self.stack[j][0] in ("i", "em")):
                del self.stack[j]
                return

    def handle_data(self, data):
        st = self._state()
        self.out += [(ch, st) for ch in data]


def _chars(b):
    """A text block's characters with their formatting, from its inline HTML (or its plain text)."""
    h = b.get("h")
    if not isinstance(h, str) or not h.strip():
        return [(ch, (0, None)) for ch in str(b.get("x") or "")]
    p = _Inline()
    try:
        p.feed(h)
        p.close()
    except Exception:  # noqa: BLE001 - odd markup: the plain text will do
        return [(ch, (0, None)) for ch in str(b.get("x") or "")]
    return p.out


def _ts(t):
    t = int(float(t or 0))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


# ---- escaping ----------------------------------------------------------------------

_ESC = re.compile(r"([\\`*\[\]$#^~])")


def _esc(s):
    """Plain text that Obsidian shows as it is: no tags (#), math ($), links, block ids or emphasis."""
    s = _ESC.sub(r"\\\1", s)
    s = re.sub(r"(?<![0-9A-Za-z])_|_(?![0-9A-Za-z])", r"\\_", s)
    s = re.sub(r"<(?=[A-Za-z/!?])", r"\\<", s)
    s = re.sub(r"&(?=#?\w+;)", "&amp;", s)
    s = s.replace("==", r"\=\=").replace("%%", r"\%\%")
    return s


def _line_start(s):
    """A line that would otherwise read as a list, a quote, a heading, a rule or a table."""
    if re.match(r"^\s*(-+|=+|(\\=)+=?)\s*$", s):               # "---" is a rule, and under a line it makes a heading
        return "\\" + s.lstrip() if not s.lstrip().startswith("\\") else s
    m = re.match(r"^(\s*)(?:([>+|-])|(\d+)([.)]))(?=\s|$)", s)
    if not m:
        return s
    esc = m.group(2) and "\\" + m.group(2) or m.group(3) + "\\" + m.group(4)
    return m.group(1) + esc + s[m.end():]


def _url(u):
    return (u or "").replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("<", "%3C").replace(">", "%3E")


def _wrap(s, left, right=None):
    """s between markers, its outer spaces kept outside them (`** a **` isn't bold)."""
    lead, trail, core = s[:len(s) - len(s.lstrip())], s[len(s.rstrip()):], s.strip()
    return lead + left + core + (left if right is None else right) + trail if core else s


def _runs(items, key):
    """Consecutive items with the same key."""
    out = []
    for it in items:
        k = key(it)
        if out and out[-1][0] == k:
            out[-1][1].append(it)
        else:
            out.append((k, [it]))
    return out


# Outermost first: the highlight, then a link; then italic, bold and strikethrough, whichever of them
# runs longest outside, so "*a **b** c*" and "**a *b* c**" both nest instead of closing and reopening.
_MARK, _HREF = (lambda c: c[2]), (lambda c: c[1][1])
_FMTS = {_ITAL: "*", _BOLD: "**", _STRIKE: "~~"}


def _emit(items, layers=None):
    if layers is None:
        return "".join(_wrap(_emit(r, ["href"]), "==") if k else _emit(r, ["href"]) for k, r in _runs(items, key=_MARK))
    if layers == ["href"]:
        return "".join(_wrap(_emit(r, list(_FMTS)), "[", f"]({_url(k)})") if k else _emit(r, list(_FMTS))
                       for k, r in _runs(items, key=_HREF))
    if not layers:
        out = []
        for code, r in _runs(items, key=lambda c: bool(c[1][0] & _CODE)):
            t = "".join(c[0] for c in r)
            out.append(_wrap(t, "``" if "`" in t else "`") if code and t.strip() else _esc(t))
        return "".join(out)
    bit = min(layers, key=lambda f: len(_runs(items, key=lambda c: bool(c[1][0] & f))))
    rest = [f for f in layers if f != bit]
    out = []
    for k, r in _runs(items, key=lambda c: bool(c[1][0] & bit)):
        inner = _emit(r, rest)
        out.append(_wrap(inner, _FMTS[bit]) if k and inner.strip() else inner)
    return "".join(out)


def _punct(ch):
    return unicodedata.category(ch)[0] in "PS"


def _fit_marks(chars, marks):
    """A mark can't close between punctuation and a letter ('he said, “==Go'), or open between a
    letter and punctuation: such edge punctuation goes outside it."""
    marks = list(marks)
    n, i = len(marks), 0
    while i < n:
        if not marks[i]:
            i += 1
            continue
        a = i
        while i < n and marks[i]:
            i += 1
        z = i
        while z > a and _punct(chars[z - 1][0]) and z < n and chars[z][0].isalnum():
            z -= 1
            marks[z] = False
        while a < z and _punct(chars[a][0]) and a > 0 and chars[a - 1][0].isalnum():
            marks[a] = False
            a += 1
    return marks


def _line_md(chars, marks, drop=0):
    """One line of [(char, (bits, href))] with marked positions → Markdown. drop: formats left out
    (bold, in a heading)."""
    marks = _fit_marks(chars, marks)
    return _emit([(ch, (st[0] & ~drop, st[1]), mk) for (ch, st), mk in zip(chars, marks)])


# ---- blocks as pieces ----------------------------------------------------------------
# A block is a list of pieces: ("lab", text, markdown) is counted where the reader counts it but
# written as given and never marked (a verse's number, a speaker's name), ("txt", chars) is the
# text, ("nl",) a new line. Its plain text, for placing highlights, is every piece's text in order.

def _pieces(b):
    t = b.get("t")
    if t == "verse":
        he = [(ch, (0, None)) for ch in str(b.get("he") or "")]
        return [("lab", str(b.get("n") or ""), f"**{b.get('n')}** " if b.get("n") else ""), ("txt", he), ("nl",), ("txt", _chars(b))]
    if t == "cue":
        out = []
        if b.get("spk") and b.get("spk") != "None":
            out.append(("lab", str(b["spk"]) + " ", f"**{_esc(str(b['spk']))}:** "))
        return out + [("txt", _chars(b))]
    if t == "h3" and b.get("ts") is not None:
        return [("lab", _ts(b["ts"]) + " ", ""), ("txt", _chars(b))]
    return [("txt", _chars(b))]


def _plain(pieces):
    return "".join(p[1] if p[0] == "lab" else "".join(c for c, _ in p[1]) if p[0] == "txt" else "" for p in pieces)


def _norm(s):
    """Text compared for placing: no whitespace, lower case, straight quotes, one char per char."""
    tr = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}
    out, idx = [], []
    for i, ch in enumerate(s):
        ch = tr.get(ch, ch)
        if ch.isspace():
            continue
        lo = ch.lower()
        out.append(lo if len(lo) == 1 else ch)
        idx.append(i)
    return "".join(out), idx


# ---- placing highlights ---------------------------------------------------------------

class Doc:
    """A document's blocks, ready to place highlights in and write out."""

    def __init__(self, blocks, kind=None, url=None):
        self.blocks = [b for b in (blocks or []) if isinstance(b, dict)]
        self.kind, self.url = kind, url
        self.pieces = [None if b.get("t") in ("img", "pg") else _pieces(b) for b in self.blocks]
        self.plain = [_plain(p) if p is not None else "" for p in self.pieces]
        self.norm = [_norm(p) for p in self.plain]
        self.marks = {}            # block → set of marked plain-text positions
        self.anchor = {}           # highlight id → block its link goes to
        self.start = {}            # highlight id → (block, position), for reading order
        self.skip = self._junk()
        self._stream = None

    def _junk(self):
        if self.kind != "tweet":
            return set()
        seen = {}
        for b in self.blocks:
            if b.get("t") == "img":
                seen[b.get("src")] = seen.get(b.get("src"), 0) + 1
        return {i for i, b in enumerate(self.blocks)
                if (b.get("t") == "img" and (seen.get(b.get("src"), 0) > 1 or "/profile_images/" in str(b.get("src")))) or (b.get("t") != "img" and XJUNK.match(str(b.get("x") or "").strip()))}

    def _mark(self, hid, spans):
        for i, a, z in spans:
            if z > a:
                self.marks.setdefault(i, set()).update(range(a, z))
        if spans:
            self.anchor[hid] = spans[0][0]
            self.start[hid] = (spans[0][0], spans[0][1])

    def place(self, hid, text, pos):
        """Mark one highlight. Returns the block it was found in, or None."""
        pos = pos if isinstance(pos, dict) else {}
        text = (text or "").strip()
        m = re.match(r"^!\[[^\]]*\]\((\S+?)\)$", text)
        if m or pos.get("img"):
            src = pos.get("img") or m.group(1)
            for i, b in enumerate(self.blocks):
                if b.get("t") == "img" and b.get("src") == src:
                    self.anchor[hid], self.start[hid] = i, (i, 0)
                    return i
            return None
        spans = self._by_offsets(text, pos) or self._by_words(text, pos.get("pre"))
        self._mark(hid, spans or [])
        return spans[0][0] if spans else None

    def _by_offsets(self, text, pos):
        b, s, e = pos.get("b"), pos.get("s"), pos.get("e")
        if not isinstance(b, int) or not isinstance(s, int) or not isinstance(e, int) or not 0 <= b < len(self.blocks):
            return None
        be = pos.get("be") if isinstance(pos.get("be"), int) and pos["be"] >= b else b
        if be >= len(self.blocks):
            return None
        spans, got = [], ""
        for i in range(b, be + 1):
            if self.pieces[i] is None:
                continue
            x = self.plain[i]
            a = s if i == b else 0
            z = e if i == be else len(x)
            # From the reader's or the block's offsets to these characters: by non-space characters.
            na, nz = len(_norm(x[:max(0, a)])[0]), len(_norm(x[:max(0, z)])[0])
            idx = self.norm[i][1]
            if na >= len(idx):
                continue
            pa = idx[na]
            pz = idx[nz - 1] + 1 if 0 < nz <= len(idx) else len(x)
            spans.append((i, pa, pz))
            got += x[pa:pz]
        want = _norm(text)[0]
        g = _norm(got)[0]
        # The offsets still fit when the words there are the highlight's (allowing for a word or so at the edges).
        if not want or not g or not (g == want or (len(want) > 12 and want[:12] in g and want[-12:] in g)):
            return None
        return spans

    def _stream_of(self):
        if self._stream is None:
            chars, back = [], []
            for i, (n, idx) in enumerate(self.norm):
                if i in self.skip or self.pieces[i] is None:
                    continue
                chars.append(n)
                back += [(i, p) for p in idx]
            self._stream = ("".join(chars), back)
        return self._stream

    def _by_words(self, text, pre=None):
        want = _norm(text)[0]
        if len(want) < 2:
            return None
        hay, back = self._stream_of()
        at = [m.start() for m in re.finditer(re.escape(want), hay)]
        if len(at) > 1 and pre:
            p = _norm(pre)[0][-24:]
            at = [a for a in at if p and hay[max(0, a - len(p)):a].endswith(p)] or at
        if at:
            a, z = at[0], at[0] + len(want)
        elif len(want) > 80:                 # the words drifted a little (a Kindle copy): by the ends
            a = hay.find(want[:40])
            z = hay.find(want[-40:], a + 40) + 40 if a >= 0 else -1
            if a < 0 or z < 40 or z - a > 3 * len(want):
                return None
        else:
            return None
        spans = {}
        for k in range(a, z):
            i, p = back[k]
            lo, hi = spans.get(i, (p, p + 1))
            spans[i] = (min(lo, p), max(hi, p + 1))
        return [(i, lo, hi) for i, (lo, hi) in sorted(spans.items())]

    # ---- writing ---------------------------------------------------------------------

    def _yt(self):
        from . import media
        return media.youtube_id(self.url) if self.url else None

    def _block_md(self, i):
        b = self.blocks[i]
        t = b.get("t")
        if t == "img":
            src = str(b.get("src") or "")
            if not src.startswith(("http://", "https://")):
                return None
            alt = re.sub(r"\s+", " ", re.sub(r"[\[\]|\n]+", " ", str(b.get("alt") or ""))).strip()
            return f"![{_esc(alt)}]({_url(src)})"
        if t == "pg":
            return f"*— p. {b.get('pg') or b.get('h')} —*"
        pieces = self.pieces[i]
        marked = self.marks.get(i, set())
        lines, cur, cur_m, pos = [], [], [], 0
        prefix = ""
        for p in pieces:
            if p[0] == "lab":
                if not lines and not cur:
                    prefix += p[2]
                pos += len(p[1])
            elif p[0] == "nl":
                lines.append((cur, cur_m))
                cur, cur_m = [], []
            else:
                for ch, st in p[1]:
                    if ch == "\n":
                        lines.append((cur, cur_m))
                        cur, cur_m = [], []
                    else:
                        cur.append((ch, st))
                        cur_m.append(pos in marked)
                    pos += 1
        lines.append((cur, cur_m))
        drop = _BOLD if t in ("h2", "h3") else 0
        md = [re.sub(r"[ \t]+", " ", _line_md(c, m, drop)).strip() for c, m in lines]
        md = [s for s in md if s]
        if not md:
            return None
        md[0] = prefix + md[0]
        if t == "cue" and b.get("ts") is not None:
            vid = self._yt()
            when = _ts(b["ts"])
            stamp = f"[{when}](https://www.youtube.com/watch?v={vid}&t={int(float(b['ts']))}s)" if vid else f"**{when}**"
            md[0] = f"{stamp} {md[0]}"
        if t in ("h2", "h3"):
            head = " ".join(md)
            if b.get("ts") is not None:
                head += f" ({_ts(b['ts'])})"
            return ("### " if t == "h2" else "#### ") + head
        if t == "li":
            return "- " + "\n  ".join(_line_start(s) for s in md)
        if t == "blockquote":
            return "\n".join("> " + _line_start(s) for s in md)
        if t == "dt":
            return "**" + " ".join(md) + "**"
        md = [_line_start(s) for s in md]
        if t == "figcaption" and not any("*" in s for s in md):
            md = [f"*{s}*" for s in md]
        return "\n".join(md)

    def markdown(self, more_link=None, limit=FULL_TEXT_MAX, lo=0, hi=None):
        """The text of blocks lo to hi (all of it by default). Past the limit, the highlighted
        blocks only, with … between them."""
        anchored = set(self.marks) | set(self.anchor.values())
        out, size, cut, gap, dropped, prev = "", 0, False, False, False, None
        for i in range(lo, len(self.blocks) if hi is None else hi):
            b = self.blocks[i]
            if i in self.skip:
                continue
            if cut and i not in anchored:
                gap = dropped = True
                continue
            md = self._block_md(i)
            if md is None:
                continue
            if i in anchored and b.get("t") not in ("h2", "h3"):
                md += f" ^daf-b{i}"
            if gap:
                out += "\n\n…"
                gap = False
            # List items stay together; everything else is its own paragraph.
            out += ("" if not out else "\n" if prev == "li" and b.get("t") == "li" else "\n\n") + md
            size += len(md) + 2
            prev = b.get("t")
            if size > limit:
                cut = True
        if dropped:
            out += "\n\n*The rest of the text is in Daf" + (f": [open it there]({more_link})" if more_link else "") + ".*"
        return out
