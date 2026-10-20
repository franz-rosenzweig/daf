"""Where a highlight opens, and the order highlights come in a book.

Every highlight row gets an `open` link: the exact spot in Daf's book reader when Calibre has
a file for the book (Daf's own highlights by CFI, the Kindle's by KOReader's xpointer, audiobook
and paper ones by their text), the article or video in the reading view, and otherwise the
book's page in Daf with that highlight picked out.
"""
import json
import re
from urllib.parse import quote

from . import ebooks

XP = re.compile(r"DocFragment\[(\d+)\]")


def _q(s):
    return quote(str(s), safe="")


def href(r, readable, docs):
    b, hid = r.get("book_id"), r.get("id")
    if not b or not hid:
        return None
    if b in docs:
        p = pos_of(r)
        if p.get("pdf") and p.get("b") is None:          # made on the PDF's page, not found in its text
            return f"#pdf/{_q(b)}/hl:{_q(hid)}"
        return f"#read/{_q(b)}/hl:{_q(hid)}"
    if b in readable:
        return f"#ebook/{_q(b)}/hl:{_q(hid)}"
    return f"#book/{_q(b)}/hl:{_q(hid)}"


def pos_of(r):
    p = r.get("pos")
    if isinstance(p, dict):
        return p
    if isinstance(p, str) and p.startswith("{"):
        try:
            return json.loads(p)
        except ValueError:
            return {}
    return {"xp": p} if isinstance(p, str) and p else {}


def order(r):
    """A number that sorts a book's highlights into reading order, whatever made them."""
    p = pos_of(r)
    if p.get("fraction") is not None:
        return float(p["fraction"]) * 1e6
    if p.get("b") is not None:
        return float(p["b"]) * 1e4 + float(p.get("s") or 0)
    if isinstance(p.get("pdf"), dict):
        r0 = (p["pdf"].get("r") or [[0, 0]])[0]
        return float(p["pdf"].get("pg") or 0) * 1e4 + float(r0[1] if len(r0) > 1 else 0) * 1e3
    if p.get("t") is not None:
        return float(p["t"])
    if r.get("page"):
        return float(r["page"]) * 1000
    m = XP.search(p.get("xp") or "")
    if m:
        return float(m.group(1)) * 1e5
    return float(r.get("created") or 0) / 1e4


def add(conn, rows, readable=None):
    """Set `open`, `order` and parsed `tags` on highlight dicts (in place); returns them."""
    if not rows:
        return rows
    readable = ebooks.readable_ids(conn) if readable is None else readable
    ids = list({r["book_id"] for r in rows if r.get("book_id")})
    docs = set()
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        docs |= {x[0] for x in conn.execute(f"SELECT id FROM docs WHERE id IN ({','.join('?' * len(chunk))})", chunk)}
    for r in rows:
        r["open"] = href(r, readable, docs)
        r["order"] = order(r)
        t = r.get("tags")
        if isinstance(t, str):
            try:
                r["tags"] = json.loads(t)
            except ValueError:
                r["tags"] = []
        elif t is None:
            r["tags"] = []
    return rows
