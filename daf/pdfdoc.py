"""PDFs in the Library: Daf keeps a copy, reads its text into paragraphs (so highlights,
read-aloud, Ask and reading time work as for articles), and serves the file for the
original layout. The copy comes from Karakeep's asset when it has one, else the URL."""
import html
import json
import re
import time
import urllib.error
import urllib.request

from . import config, content
from .sources import karakeep

DIR = config.STATE / "pdf"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def path_for(doc_id):
    return DIR / (re.sub(r"[^\w.-]", "_", doc_id) + ".pdf")


def _fetch(url):
    """A certificate made for the bare domain is common on university sites: try the other
    spelling of the host before giving up (never skip verification)."""
    def get(u):
        req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read(80_000_000)
    try:
        return get(url)
    except urllib.error.URLError as e:
        if "CERTIFICATE" not in str(e):
            raise
        alt = re.sub(r"^(https://)www\.", r"\1", url) if "://www." in url else re.sub(r"^(https://)", r"\1www.", url)
        return get(alt)


def download(conn, doc_id):
    d = conn.execute("SELECT * FROM docs WHERE id = ?", (doc_id,)).fetchone()
    if not d:
        raise KeyError(doc_id)
    DIR.mkdir(parents=True, exist_ok=True)
    dest = path_for(doc_id)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    data = None
    if doc_id.startswith("kk:"):
        try:
            b = karakeep._req("GET", f"/bookmarks/{doc_id[3:]}")
            c = b.get("content") or {}
            aid = c.get("assetId") if c.get("assetType") == "pdf" else None
            aid = aid or next((a.get("id") for a in b.get("assets", []) if "pdf" in str(a.get("assetType", "")).lower()), None)
            if aid:
                data = karakeep.asset_bytes(aid)
        except Exception:  # noqa: BLE001 - fall back to the URL
            data = None
    if not data and d["url"]:
        data = _fetch(d["url"])
    if not data or not data.startswith(b"%PDF"):
        raise RuntimeError("that link didn't give a PDF")
    dest.write_bytes(data)
    return dest


def _paragraphs(text):
    """pypdf gives lines; join them back into paragraphs."""
    lines = [l.rstrip() for l in text.splitlines()]
    widths = sorted(len(l) for l in lines if l.strip())
    full = widths[int(len(widths) * 0.8)] if widths else 80
    paras, cur = [], ""
    for l in lines:
        s = l.strip()
        if not s:
            if cur:
                paras.append(cur)
                cur = ""
            continue
        if re.fullmatch(r"\d{1,4}", s):            # a bare page number
            continue
        if cur.endswith("-") and s[:1].islower():
            cur = cur[:-1] + s
        else:
            cur = (cur + " " + s).strip()
        # A short line that ends a sentence ends the paragraph.
        if len(s) < full * 0.72 and re.search(r"[.?!:\"”’)]$", s):
            paras.append(cur)
            cur = ""
    if cur:
        paras.append(cur)
    return [p for p in paras if len(p) > 1]


def build(conn, doc_id):
    from pypdf import PdfReader
    p = download(conn, doc_id)
    reader = PdfReader(str(p))
    raw = []
    for page in reader.pages:
        try:
            raw.append([l for l in (page.extract_text() or "").splitlines()])
        except Exception:  # noqa: BLE001 - one bad page shouldn't lose the rest
            raw.append([])
    # Running heads and feet: the same first or last lines (numbers aside) on many pages.
    norm = lambda t: re.sub(r"\d+", "#", t.lower()).strip()
    counts = {}
    for lines in raw:
        ne = [l for l in lines if l.strip()]
        for t in {norm(l) for l in ne[:2] + ne[-2:]}:
            counts[t] = counts.get(t, 0) + 1
    furniture = {t for t, n in counts.items() if t and n >= max(3, len(raw) * 0.4) and len(t) < 160}
    blocks = []
    for i, lines in enumerate(raw, 1):
        ne = [j for j, l in enumerate(lines) if l.strip()]
        edge = set(ne[:2] + ne[-2:])
        paras = _paragraphs("\n".join(l for j, l in enumerate(lines) if not (j in edge and norm(l) in furniture)))
        if not paras:
            continue
        blocks.append({"t": "pg", "h": str(i), "x": "", "pg": i})
        for para in paras:
            blocks.append({"t": "p", "h": html.escape(para, quote=False), "x": para, "pg": i})
    if not any(b["t"] == "p" for b in blocks):
        raise RuntimeError("no text in this PDF (a scan?); open the original")
    meta = reader.metadata or {}
    title = (meta.get("/Title") or "").strip() if hasattr(meta, "get") else ""
    if not title:
        # Papers start with their title: the first line of page 1 that reads like one.
        title = next((l.strip() for l in (raw[0] if raw else [])[:6] if norm(l) not in furniture and not re.search(r"\d", l)
                      and 4 <= len(l.split()) <= 20 and not l.strip().endswith(".")), "")
    conn.execute("INSERT OR REPLACE INTO doc_content (id, blocks, fetched) VALUES (?, ?, ?)",
                 (doc_id, json.dumps(blocks, ensure_ascii=False), int(time.time())))
    conn.execute("UPDATE docs SET words = ?, summary = COALESCE(NULLIF(summary, ''), ?), "
                 "title = CASE WHEN ? != '' AND title LIKE '%.pdf' THEN ? ELSE title END WHERE id = ?",
                 (content.words(blocks), content.summary(blocks), title, title, doc_id))
    return len(blocks)
