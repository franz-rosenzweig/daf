"""Ink: what's written with a pen on an article (web/ink.js) or a book (web/book.js), the pens being
web/pens.js. Each stroke keeps the place it was written (an article's paragraph, or a book's CFI; the
letter it started on, and where it sat beside it), so it follows the text when the type or the column
changes, and its points with the pen's pressure. The page makes each stroke's id, so a stroke written
offline and sent twice is kept once, and undo removes it by its id.

A stroke is {id, v, tool: the pen (fountain, calligraphy, pen, pencil, brush, marker, highlighter),
color ("ink", a highlight colour or #rrggbb), size (its width in px as written), o (opacity), at, pts},
and sh when it's a shape held still and made clean (not read as writing). Handwriting read as text
and put in its place is tool "text", with text, fs (its type size, px) and w (its width, px).
Round one's (no v) were tool "pen" or "marker" (the highlighter) with a named colour."""
import json
import re
import time

TOOLS = ("fountain", "calligraphy", "pen", "pencil", "brush", "marker", "highlighter", "text")
COLORS = ("ink", "blue", "red", "green", "yellow", "pink", "purple")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
ID = re.compile(r"^k[0-9a-z]{8,32}$")
MAX_POINTS = 4000


def strokes(conn, doc):
    out = []
    for r in conn.execute("SELECT id, tool, color, size, data, created FROM ink WHERE doc = ? ORDER BY created, rowid", (doc,)):
        try:
            data = json.loads(r["data"])
        except ValueError:
            continue
        s = {"id": r["id"], "tool": r["tool"], "color": r["color"], "size": r["size"], "at": data.get("at"), "pts": data.get("pts"), "created": r["created"]}
        if data.get("v"):
            s["v"], s["o"] = data["v"], data.get("o", 1)
        for k in ("sh", "text", "fs", "w"):
            if data.get(k) is not None:
                s[k] = data[k]
        out.append(s)
    return out


def _num(v, lo, hi):
    v = float(v)
    if v != v:                                  # NaN
        raise ValueError("Not a number")
    return max(lo, min(hi, v))


def _clean(s):
    """A stroke as the page sent it, checked: ValueError if it isn't one."""
    if not isinstance(s, dict) or not ID.match(str(s.get("id") or "")):
        raise ValueError("Bad stroke id")
    v = 2 if s.get("v") else None
    tool = s.get("tool") if s.get("tool") in TOOLS else "pen"
    if not v and tool not in ("pen", "marker"):
        tool = "pen"
    color = s.get("color") if s.get("color") in COLORS or HEX.match(str(s.get("color") or "")) else "ink"
    a = s.get("at") if isinstance(s.get("at"), dict) else {}
    at = {"f": _num(a.get("f") or 16, 4, 200), "x": round(_num(a.get("x") or 0, -10000, 10000), 1), "y": round(_num(a.get("y") or 0, -100000, 100000), 1)}
    if a.get("cfi"):                            # a book's: the letter it started on, as a CFI, in its section
        at.update(cfi=str(a["cfi"])[:2000], s=int(a.get("s") or 0))
    else:                                       # an article's: its paragraph, and the letter in it
        at.update(b=int(a.get("b") or 0), q=str(a.get("q") or "")[:40], w=_num(a.get("w") or 1, 1, 10000), h=_num(a.get("h") or 1, 1, 100000))
        if a.get("c") is not None:
            at["c"] = int(a["c"])
    pts = s.get("pts")
    if not isinstance(pts, list) or not pts or len(pts) > MAX_POINTS:
        raise ValueError("Bad points")
    clean = []
    for p in pts:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            raise ValueError("Bad point")
        clean.append([round(_num(p[0], -10000, 10000), 1), round(_num(p[1], -100000, 100000), 1),
                      round(_num(p[2] if len(p) > 2 else 0.5, 0, 1), 2)])
    out = {"id": s["id"], "tool": tool, "color": color, "size": round(_num(s.get("size") or 2.5, 0.3, 80), 1), "at": at, "pts": clean}
    if v:
        out["v"], out["o"] = v, round(_num(s.get("o") if s.get("o") is not None else 1, 0.05, 1), 2)
    if s.get("sh"):
        out["sh"] = 1
    if tool == "text":
        text = str(s.get("text") or "").strip()[:5000]
        if not v or not text:
            raise ValueError("No text")
        out.update(text=text, fs=round(_num(s.get("fs") or 16, 6, 120), 1), w=round(_num(s.get("w") or 120, 1, 5000), 1))
    return out


def change(conn, doc, add=(), remove=(), at=None):
    """Strokes written (add) and erased (remove, by id), in one go. Returns how many of each."""
    now = int(time.time())
    created = at if isinstance(at, int) and now - 30 * 86400 < at <= now + 60 else now
    added = 0
    for s in list(add)[:500]:
        s = _clean(s)
        data = {"at": s["at"], "pts": s["pts"]}
        if s.get("v"):
            data.update(v=s["v"], o=s["o"])
        data.update({k: s[k] for k in ("sh", "text", "fs", "w") if k in s})
        conn.execute("INSERT OR REPLACE INTO ink (id, doc, tool, color, size, data, created) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (s["id"], doc, s["tool"], s["color"], s["size"], json.dumps(data, separators=(",", ":")), created))
        added += 1
    ids = [str(i) for i in list(remove)[:2000] if ID.match(str(i))]
    removed = 0
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        removed += conn.execute(f"DELETE FROM ink WHERE doc = ? AND id IN ({','.join('?' * len(part))})", (doc, *part)).rowcount
    return added, removed
