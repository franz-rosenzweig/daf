"""Send to Kindle, the way Readwise Reader does it: articles become one EPUB (a digest when there
are several) written into the folder Syncthing shares with the Kindle (Libros/Daf), so KOReader
has it the next time the Kindle is online. Images come along, fetched once, shrunk to the
Kindle's width and kept under a budget; anything odd (a private address, a tracking pixel, too
big) is simply left out."""
import hashlib
import html
import io
import json
import ipaddress
import os
import socket
import urllib.parse
import urllib.request
import re
import time
import uuid
import zipfile
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

from . import reader

KINDLE_DIR = Path(os.environ.get("DAF_KINDLE_DIR", "/srv/koreader/Libros/Daf"))
INLINE = {"a", "em", "i", "strong", "b", "code", "sub", "sup", "s", "u", "small", "mark", "q", "abbr", "cite", "span"}
HEBREW = re.compile(r"[֐-׿]")


class _Clean(HTMLParser):
    """A block's inline HTML as well-formed XHTML: only inline tags, no attributes but a link's
    href, every tag closed, every entity resolved."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.open = [], []

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.out.append("<br/>")
        elif tag in INLINE:
            href = dict(attrs).get("href") if tag == "a" else None
            self.out.append(f'<{tag} href="{html.escape(href, quote=True)}">' if href and href.startswith("http") else f"<{tag}>")
            self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in self.open:
            while self.open:
                t = self.open.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        self.out.append(html.escape(data, quote=False))

    def result(self):
        return "".join(self.out) + "".join(f"</{t}>" for t in reversed(self.open))


def _inline(b):
    if b.get("h"):
        p = _Clean()
        p.feed(b["h"])
        p.close()
        return p.result()
    return html.escape(b.get("x") or "", quote=False)


IMG_MAX_BYTES = 4_000_000          # one image as downloaded
IMG_BUDGET = 20_000_000            # all images in one EPUB, as stored
IMG_MAX_COUNT = 60
IMG_WIDTH = 1200                   # about the Kindle's screen


def _public(host):
    """True when every address the host resolves to is a public one (no fetching from inside)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        # is_global, not just "not private": the tailnet's 100.64.0.0/10 isn't private to Python either
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to another public address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme not in ("http", "https") or not u.hostname or not _public(u.hostname):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_PublicRedirects)


def _fetch_image(url):
    """(bytes, media type, extension) of an image made ready for the Kindle, or None."""
    from PIL import Image
    u = urllib.parse.urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname or not _public(u.hostname):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Daf; Send to Kindle)", "Accept": "image/*"})
    try:
        with _OPENER.open(req, timeout=8) as r:
            data = r.read(IMG_MAX_BYTES + 1)
    except Exception:  # noqa: BLE001 - one missing image must not stop the EPUB
        return None
    if len(data) > IMG_MAX_BYTES:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:  # noqa: BLE001 - not an image Pillow can read
        return None
    if im.width < 40 or im.height < 40:            # a tracking pixel or an icon
        return None
    if im.width > IMG_WIDTH:
        im = im.resize((IMG_WIDTH, round(im.height * IMG_WIDTH / im.width)))
    out = io.BytesIO()
    if im.mode in ("RGBA", "LA", "P") and (im.mode != "P" or "transparency" in im.info):
        im.convert("RGBA").save(out, "PNG", optimize=True)
        return out.getvalue(), "image/png", "png"
    im.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue(), "image/jpeg", "jpg"


class _Images:
    """Collects the images for one EPUB, fetched six at a time up front."""

    def __init__(self, urls=()):
        from concurrent.futures import ThreadPoolExecutor
        self.files, self.total = [], 0
        urls = list(dict.fromkeys(u for u in urls if u))[:IMG_MAX_COUNT * 2]
        with ThreadPoolExecutor(6) as pool:
            self.got = dict(zip(urls, pool.map(_fetch_image, urls)))

    def add(self, url):
        if len(self.files) >= IMG_MAX_COUNT or self.total >= IMG_BUDGET:
            return None
        got = self.got.get(url)
        if not got or self.total + len(got[0]) > IMG_BUDGET:
            return None
        data, mt, ext = got
        name = f"images/img{len(self.files) + 1}.{ext}"
        self.files.append((name, data, mt))
        self.total += len(data)
        return name


def _chapter(d, blocks, images=None):
    rtl = bool(HEBREW.search(d["title"] or "")) or sum(1 for b in blocks[:8] if HEBREW.search(b.get("x") or "")) >= 3
    meta = " · ".join(html.escape(x) for x in (d.get("author"), d.get("source")) if x)
    body = [f"<h1>{html.escape(d['title'] or 'Untitled')}</h1>"]
    if meta:
        body.append(f'<p class="meta">{meta}</p>')
    in_list = False
    for b in blocks:
        t = b.get("t")
        if t == "img":
            name = images.add(b.get("src")) if images is not None else None
            if name:
                if in_list:
                    body.append("</ul>")
                    in_list = False
                body.append(f'<div class="fig"><img src="{name}" alt="{html.escape(b.get("alt") or "", quote=True)}"/></div>')
            continue
        if t == "li" and not in_list:
            body.append("<ul>")
            in_list = True
        elif t != "li" and in_list:
            body.append("</ul>")
            in_list = False
        tag = {"h1": "h2", "h2": "h2", "h3": "h3", "h4": "h4", "blockquote": "blockquote", "li": "li", "figcaption": "p"}.get(t, "p")
        cls = ' class="cap"' if t == "figcaption" else ""
        inner = _inline(b)
        if inner.strip():
            body.append(f"<{tag}{cls}>{inner}</{tag}>" if tag != "blockquote" else f"<blockquote><p>{inner}</p></blockquote>")
    if in_list:
        body.append("</ul>")
    if d.get("url"):
        body.append(f'<p class="src"><a href="{html.escape(d["url"], quote=True)}">{html.escape(d["url"])}</a></p>')
    lang = "he" if rtl else "en"
    dir_attr = ' dir="rtl"' if rtl else ""
    return lang, (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" lang="{lang}"'
                  f'{dir_attr}><head><meta charset="utf-8"/><meta name="daf-doc" content="{html.escape(d["id"], quote=True)}"/>'
                  f'<title>{html.escape(d["title"] or "")}</title>'
                  f'<link rel="stylesheet" href="style.css" type="text/css"/></head><body>{"".join(body)}</body></html>')


CSS = """body{font-family:serif;line-height:1.45;margin:0 4%}
h1{font-size:1.5em;line-height:1.2;margin:0.6em 0 0.2em}
h2{font-size:1.2em;margin:1.2em 0 0.4em} h3,h4{font-size:1.05em;margin:1em 0 0.3em}
p{margin:0 0 0.7em;text-indent:0} .meta{color:#555;font-size:0.9em;margin-bottom:1.4em}
.cap{font-size:0.85em;color:#555;font-style:italic} .src{font-size:0.8em;color:#555;margin-top:2em;word-break:break-all}
blockquote{margin:0.8em 1.2em;font-style:italic} ul{margin:0 0 0.8em 1.2em}
.fig{margin:1em 0;text-align:center} .fig img{max-width:100%;height:auto}
"""


def _slug(s, n=60):
    s = re.sub(r"[^\w\s.,'’()-]+", "", s or "").strip()
    return re.sub(r"\s+", " ", s)[:n].strip() or "Daf"


def make_epub(conn, ids, when=None):
    """Write the EPUB for these documents into KINDLE_DIR. Returns {file, title, count, skipped}."""
    docs, skipped = [], []
    for i in ids:
        d = reader.get_doc(conn, i, prefetch=True)
        blocks = (d or {}).get("blocks") or []
        if not d or not any(b.get("t") != "img" for b in blocks):
            skipped.append(i)
            continue
        docs.append((d, blocks))
    if not docs:
        raise ValueError("None of these has text Daf can send")
    when = when or datetime.now()
    if len(docs) == 1:
        title = docs[0][0]["title"] or "Untitled"
        fname = f"{_slug(title)} (Daf).epub"
    else:
        title = f"Daf digest, {when.strftime('%B')} {when.day}, {when.year}"
        fname = f"Daf digest {when.strftime('%Y-%m-%d %H%M')} ({len(docs)} articles).epub"
    uid = "urn:uuid:" + str(uuid.uuid4())
    images = _Images(b.get("src") for _, bl in docs for b in bl if b.get("t") == "img")
    chapters = [_chapter(d, bl, images) for d, bl in docs]
    lang = "he" if all(c[0] == "he" for c in chapters) else "en"
    items = "".join(f'<item id="c{n}" href="c{n}.xhtml" media-type="application/xhtml+xml"/>' for n in range(1, len(chapters) + 1))
    items += "".join(f'<item id="i{n}" href="{name}" media-type="{mt}"/>' for n, (name, _, mt) in enumerate(images.files, 1))
    spine = "".join(f'<itemref idref="c{n}"/>' for n in range(1, len(chapters) + 1))
    opf = (f'<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">'
           f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">{uid}</dc:identifier>'
           f'<dc:title>{html.escape(title)}</dc:title><dc:creator>{html.escape(docs[0][0].get("author") or "Daf") if len(docs) == 1 else "Daf"}</dc:creator>'
           f'<dc:language>{lang}</dc:language><dc:publisher>Daf</dc:publisher>'
           f'<meta property="dcterms:modified">{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}</meta></metadata>'
           f'<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           f'<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/><item id="css" href="style.css" media-type="text/css"/>{items}</manifest>'
           f'<spine toc="ncx">{spine}</spine></package>')
    names = [html.escape(d["title"] or "Untitled") for d, _ in docs]
    nav = ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
           f'<head><title>{html.escape(title)}</title></head><body><nav epub:type="toc"><h1>{html.escape(title)}</h1><ol>'
           + "".join(f'<li><a href="c{n}.xhtml">{t}</a></li>' for n, t in enumerate(names, 1)) + '</ol></nav></body></html>')
    ncx = (f'<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="{uid}"/></head>'
           f'<docTitle><text>{html.escape(title)}</text></docTitle><navMap>'
           + "".join(f'<navPoint id="n{n}" playOrder="{n}"><navLabel><text>{t}</text></navLabel><content src="c{n}.xhtml"/></navPoint>' for n, t in enumerate(names, 1))
           + "</navMap></ncx>")
    KINDLE_DIR.mkdir(parents=True, exist_ok=True)
    path = KINDLE_DIR / fname
    tmp = path.with_name("." + fname + ".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, compress_type=zipfile.ZIP_DEFLATED)
        for n, (_, xhtml) in enumerate(chapters, 1):
            z.writestr(f"OEBPS/c{n}.xhtml", xhtml, compress_type=zipfile.ZIP_DEFLATED)
        for name, data, _ in images.files:
            z.writestr(f"OEBPS/{name}", data, compress_type=zipfile.ZIP_STORED)
    tmp.replace(path)
    now = int(time.time())
    conn.executemany("INSERT OR REPLACE INTO kindle_sent (doc_id, file, at) VALUES (?, ?, ?)", [(d["id"], fname, now) for d, _ in docs])
    from . import kindlequeue
    kindlequeue.queue_file(conn, path, "Daf")       # the plugin fetches it (Syncthing no longer carries Libros)
    record(conn, path)
    return {"file": fname, "title": title, "count": len(docs), "skipped": skipped, "images": len(images.files)}


def sent(conn, doc_id):
    r = conn.execute("SELECT file, at FROM kindle_sent WHERE doc_id = ?", (doc_id,)).fetchone()
    return dict(r) if r else None


# ---- what happens on the Kindle -----------------------------------------------------------
# KOReader knows a file by its partial md5, and a highlight by an xpointer whose DocFragment[n]
# is the nth chapter: the nth article. So each EPUB is recorded by that md5 with its articles
# in order, and highlights, page turns and progress on it go to the articles themselves.

DOC_META = re.compile(r'<meta name="daf-doc" content="([^"]+)"')
XP_PART = re.compile(r"DocFragment\[(\d+)\]")
IMG_WEIGHT = 600                   # an image takes about as much of a page as this many characters


def partial_md5(path):
    """KOReader's fingerprint of a book file (util.partialMD5): 1 KB at 0, 1 KB, 4 KB, 16 KB … 1 GB."""
    m = hashlib.md5()
    with open(path, "rb") as f:
        for i in range(-1, 11):
            f.seek(0 if i < 0 else 1024 << (2 * i))
            chunk = f.read(1024)
            if not chunk:
                break
            m.update(chunk)
    return m.hexdigest()


def record(conn, path):
    """Note a Daf EPUB's md5 and its articles (read back from the file, so a rebuilt index can
    find them again). Returns the md5, or None for a file Daf didn't make."""
    try:
        parts = []
        with zipfile.ZipFile(path) as z:
            names = sorted((n for n in z.namelist() if re.fullmatch(r"OEBPS/c\d+\.xhtml", n)), key=lambda n: int(n[7:-6]))
            for n in names:
                x = z.read(n).decode("utf-8", "replace")
                m = DOC_META.search(x)
                if not m:
                    return None
                body = x.split("<body>", 1)[-1]
                parts.append([html.unescape(m.group(1)), len(re.sub(r"<[^>]+>", "", body)) + IMG_WEIGHT * body.count("<img ")])
        if not parts:
            return None
        md5 = partial_md5(path)
    except (OSError, zipfile.BadZipFile):
        return None
    conn.execute("INSERT OR REPLACE INTO kindle_epubs (md5, file, parts) VALUES (?, ?, ?)",
                 (md5, Path(path).name, json.dumps(parts, ensure_ascii=False)))
    return md5


def scan(conn):
    """Record any Daf EPUB in the Kindle folder the index doesn't know yet."""
    known = {r[0] for r in conn.execute("SELECT file FROM kindle_epubs")}
    for p in KINDLE_DIR.glob("*.epub") if KINDLE_DIR.is_dir() else ():
        if p.name not in known and not p.name.startswith(".") and ".sync-conflict-" not in p.name:
            record(conn, p)


def epubs(conn):
    """{md5: [[doc id, length], …]} for every EPUB Send to Kindle wrote."""
    return {r[0]: json.loads(r[1]) for r in conn.execute("SELECT md5, parts FROM kindle_epubs")}


def part_at(parts, page, total):
    """(doc id, how far through it, 0–1) for a page of the EPUB, from each article's share of
    the text. KOReader's pages depend on the font, so this is close, not exact."""
    if not page or not total or not parts:
        return None
    whole = sum(w for _, w in parts) or 1
    mid, end = (page - 0.5) / total, min(1.0, page / total)
    lo = 0.0
    for n, (doc, w) in enumerate(parts):
        hi = lo + w / whole
        if mid < hi or n == len(parts) - 1:
            return doc, max(0.0, min(1.0, (end - lo) / ((hi - lo) or 1)))
        lo = hi
    return None


def doc_for(parts, annotation, titles=None):
    """The article a KOReader highlight was made in: by its xpointer, else by its chapter title."""
    m = XP_PART.search(str(annotation.get("pos0") or annotation.get("page") or ""))
    if m and 1 <= int(m.group(1)) <= len(parts):
        return parts[int(m.group(1)) - 1][0]
    ch = re.sub(r"\s+", " ", str(annotation.get("chapter") or "")).strip().lower()
    for doc, _ in parts:
        if ch and ch == re.sub(r"\s+", " ", (titles or {}).get(doc) or "").strip().lower():
            return doc
    return parts[0][0] if len(parts) == 1 else None


def place(blocks, text):
    """Where a Kindle highlight sits in the article's text, found by its words: {b, s, e}, with be
    when it runs on into later paragraphs (as Daf's own highlights are stored), or None."""
    words = (text or "").split()
    if not words:
        return None
    texts = [(i, b.get("x") or "") for i, b in enumerate(blocks) if b.get("t") != "img"]
    tail = re.compile(r"\s+".join(map(re.escape, words[-6:])))
    # The first ten words, then fewer, for a highlight that starts at the end of a paragraph.
    for n in sorted({min(10, len(words)), min(4, len(words)), min(2, len(words))}, reverse=True):
        head = re.compile(r"\s+".join(map(re.escape, words[:n])))
        for k, (i, x) in enumerate(texts):
            m = head.search(x)
            if not m:
                continue
            if n == len(words):
                return {"b": i, "s": m.start(), "e": m.end()}
            t = tail.search(x, m.start())
            if t:
                return {"b": i, "s": m.start(), "e": max(t.end(), m.end())}
            for j, y in texts[k + 1:k + 40]:
                t = tail.search(y)
                if t:
                    return {"b": i, "s": m.start(), "e": t.end(), "be": j}
            return {"b": i, "s": m.start(), "e": len(x)}
    return None
