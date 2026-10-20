"""Turn article HTML (from FreshRSS or Karakeep) into a clean list of blocks.

A block is {"t": tag, "h": safe inline html, "x": plain text} for paragraphs,
headings, quotes, list items and preformatted text, or {"t": "img", "src", "alt"}.
Highlights are stored as (block index, start, end) over "x", so the reader and the
vault agree on what was highlighted even if the page's HTML changes later.
"""
import html
import re
from html.parser import HTMLParser

BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li", "pre", "figcaption", "dd", "dt"}
INLINE = {"a", "em", "i", "strong", "b", "code", "sup", "sub", "mark", "s", "u", "small"}
SKIP = {"script", "style", "noscript", "iframe", "svg", "form", "button", "nav", "footer", "header", "aside", "select", "template"}
CONTAINERS = {"div", "section", "article", "main", "td", "figure", "ul", "ol", "dl", "table", "tbody", "tr", "span", "body", "html", "center"}


class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.cur, self.tag, self.skip, self.stack = [], None, None, 0, []

    def _start_block(self, tag):
        self._end_block()
        self.cur, self.tag = [], tag

    def _end_block(self):
        if self.cur is not None:
            h = "".join(self.cur).strip()
            x = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", h))).strip()
            if x:
                t = "h2" if self.tag in ("h1", "h2") else "h3" if self.tag in ("h3", "h4", "h5", "h6") else self.tag
                self.blocks.append({"t": t, "h": re.sub(r"\s+", " ", h), "x": x})
        self.cur, self.tag = None, None

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src.startswith(("http://", "https://")) and not re.search(r"(pixel|tracking|feeds\.feedburner|\.gif\?)", src):
                self._end_block()
                self.blocks.append({"t": "img", "src": src, "alt": (a.get("alt") or "")[:200]})
            return
        if tag == "br":
            if self.cur is not None:
                self.cur.append("<br>")
            return
        if tag in BLOCKS:
            self._start_block(tag)
            return
        if tag in INLINE and self.cur is not None:
            if tag == "a":
                href = a.get("href") or ""
                if href.startswith(("http://", "https://")):
                    self.cur.append(f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">')
                    self.stack.append("a")
                else:
                    self.stack.append(None)
                return
            t = {"b": "strong", "i": "em"}.get(tag, tag)
            self.cur.append(f"<{t}>")
            self.stack.append(t)
            return
        if tag in CONTAINERS and self.cur is not None and tag not in ("span",):
            # a div inside a paragraph-less container: start a fresh block on its text
            pass

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in BLOCKS:
            self._end_block()
            return
        if tag in INLINE and self.cur is not None and self.stack:
            t = self.stack.pop()
            if t:
                self.cur.append(f"</{t}>")
            return
        if tag in CONTAINERS and tag not in ("span",):
            self._end_block()

    def handle_data(self, data):
        if self.skip:
            return
        if self.cur is None:
            if not data.strip():
                return
            self._start_block("p")     # loose text in a container becomes a paragraph
        self.cur.append(html.escape(data, quote=False))

    def close(self):
        super().close()
        self._end_block()
        return self.blocks


def blocks(raw_html):
    p = _P()
    try:
        p.feed(raw_html or "")
    except Exception:  # noqa: BLE001 - broken markup still gives what was parsed
        pass
    out = p.close()
    # Drop boilerplate: share prompts, a repeated title, empty quotes.
    cleaned = []
    for b in out:
        if b["t"] != "img" and len(b["x"]) < 2:
            continue
        if b["t"] != "img" and re.match(r"^(share|tweet|subscribe|read more|advertisement)\b", b["x"], re.I) and len(b["x"]) < 40:
            continue
        cleaned.append(b)
    return cleaned


def words(bl):
    return sum(len(b["x"].split()) for b in bl if b["t"] != "img")


def summary(bl, n=280):
    for b in bl:
        if b["t"] == "p" and len(b["x"]) > 40:
            return b["x"][:n]
    return next((b["x"][:n] for b in bl if b["t"] != "img"), "")


def _md_inline(s):
    """Markdown inline -> (html, text): links keep their words, images and footnote marks go."""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[\^?\d+\\?\]", "", s)                      # footnote marks [1] / [^1]
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)            # [words](url) -> words
    s = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", s)      # [[note|alias]] -> alias
    s = re.sub(r"\[\[([^\]]+)\]\]", r"\1", s)
    s = s.replace("\\", "")
    s = re.sub("[\u0591-\u05AF\u05BD\u05C0\u05C3\u05C6]", "", s)   # cantillation: few reading fonts draw it
    text = re.sub(r"(\*\*|__|\*|_)(.+?)\1", r"\2", s).strip()
    h = html.escape(s, quote=False)
    h = re.sub(r"(\*\*|__)(.+?)\1", r"<b>\2</b>", h)
    h = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", h)
    return h.strip(), text


def md_blocks(md):
    """A vault note's Markdown as reader blocks (paragraphs, headings, quotes, list items).
    Web clippings carry furniture: image captions repeated as text, "View original" links,
    code fences inside quotes. Those are dropped."""
    md = re.sub(r"^---\n.*?\n---\n", "", md or "", flags=re.S)
    md = re.sub(r"<!-- daf -->.*?<!-- daf-end -->", "", md, flags=re.S)
    out, para, quote = [], [], []
    alts = set()

    def flush():
        for buf, t in ((para, "p"), (quote, "blockquote")):
            if buf:
                h, x = _md_inline(" ".join(buf))
                if len(x) > 1 and x not in alts:
                    out.append({"t": t, "h": h, "x": x})
                buf.clear()
    for line in md.splitlines():
        s = line.strip()
        for alt in re.findall(r"!\[([^\]]*)\]\([^)]*\)", s):
            alts.add(alt.strip())
        if s.startswith(">"):
            s = s.lstrip(">").strip()
            if not s or s.startswith("```"):
                if not s:
                    flush()
                continue
            if para:
                flush()
            quote.append(s)
            continue
        if quote:
            flush()
        if not s or s.startswith("```") or s in ("---", "***") or s.startswith("#ai-") or re.match(r"^#\w[\w-]*$", s):
            flush()
            continue
        if re.match(r"^!\[[^\]]*\]\([^)]*\)$", s) or re.match(r"^\[[^\]]{1,30}\]\([^)]*\)$", s):
            flush()
            continue                                 # a lone image, or a short lone link ("View original")
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            h, x = _md_inline(m.group(2))
            out.append({"t": "h2" if len(m.group(1)) <= 2 else "h3", "h": h, "x": x})
            continue
        m = re.match(r"^([-*+]|\d+[.)])\s+(.*)$", s)
        if m:
            flush()
            h, x = _md_inline(m.group(2))
            out.append({"t": "li", "h": h, "x": x})
            continue
        para.append(s)
    flush()
    return out


def article(html, url=None):
    """The article in a whole web page, as blocks: trafilatura finds it (fulltext.py fetches the page,
    pages.py gets it from the browser)."""
    import trafilatura
    out = trafilatura.extract(html, url=url, output_format="html", include_images=True, include_links=True,
                              include_tables=True, favor_precision=True)
    if not out or len(out) < 400:
        out = trafilatura.extract(html, url=url, output_format="html", include_images=True, include_links=True,
                                  include_tables=True, favor_recall=True) or out
    return blocks(out or "")
