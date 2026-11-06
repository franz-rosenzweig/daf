"""The Sketchbook in the vault: each item's pages are a note of their own beside the item's note
("<the item's note> — Sketchbook.md"), embedded in it, in the format of Obsidian's Ink plugin, so
the handwriting opens in Ink to write on, and shows anywhere without it.

The note: a "### <chapter>" heading a tab (General first, then the chapters or volumes in reading
order; none when there's only General), and under it the page's blocks in order:
- typed text, as paragraphs, each ending with a block id (^daf-t…);
- handwriting and drawings, as Ink's own blocks: an SVG file each (in _media/ beside the note) whose
  paths show it anywhere, and whose <metadata> holds what Ink needs to go on with it: <ink
  file-type="inkWriting|inkDrawing">, the strokes as an <ink-canvas version="0.5.0"> snapshot, and
  the handwriting as Daf read it in <transcript> (Daf reads it itself: Ink's reader needs an
  account). Embedded the way Ink embeds them (the plain-text transcript as the picture's text, then
  Ink's Edit link);
- pictures (a manga page, a PDF page) as ordinary image embeds, and what's written on one as an Ink
  drawing right under it.
A video's time stamps link to that moment.

Both ways, and nothing written over: Daf keeps the hash of every file as it last wrote (or read)
it, and what the note held then. A file still as Daf left it is rewritten freely. One changed since
(edited in Obsidian, or by Ink) is merged first, block by block, against that copy: a paragraph
edited there is taken (the vault wins), one added there becomes typed text there, one deleted there
goes; an Ink block added there comes into the page, and strokes written or erased in Ink come into
their block; what Daf changed since, that the vault didn't, stays. The note is read again just
before it's written, and left alone if it changed in between (Syncthing at work): the next change
tries again. Its front matter, once written, is the note's own.

The item's note gets only a region of Daf's own, `<!-- daf-sketchbook -->` … `<!-- daf-sketchbook-end -->`,
after Daf's other region (vaultnotes.py) when it has one: the embedded Sketchbook note. A book's
note is its vault note (made for it if it has none, as paper pages do), an article's or a video's is
its clipping note (vaultnotes.write_article), a manga series' is the note manga-sync made for it
(found by its MAL id or its title), else one of Daf's."""
import hashlib
import html
import json
import logging
import math
import re
import shutil
import threading
import time
from urllib.parse import parse_qs, urlencode, urlparse

from . import config, freehand, sketchbook as SB

log = logging.getLogger(__name__)

START, END = "<!-- daf-sketchbook -->", "<!-- daf-sketchbook-end -->"
REGION = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
DAF_END = "<!-- daf-end -->"
SUFFIX = " — Sketchbook"
MEDIA = "_media"
INK_PLUGIN, INK_CANVAS = "0.6.1", "0.5.0"      # the Ink plugin's version and its ink-canvas format (its manifest, INK_CANVAS_FORMAT_VERSION)
EDIT = "https://youtu.be/2arL1jh8ihA"          # Ink's INK_EMBED_BASE_URL: its Edit links point there
INK_LINE = re.compile(r"^ ?!\[([^\]]*)\]\(<([^>]+)>\) \[Edit (Writing|Drawing)\]\(([^)\s]+)\)\s*$")
PIC_LINE = re.compile(r"^!\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]\s*$|^!\[[^\]]*\]\(<?([^)>\s]+)>?\)\s*$")
TEXT_ID = re.compile(r"\s\^daf-t([0-9a-f]{8})[ \t]*$")
STAMP = re.compile(r"^(?:\[\d+(?::\d\d){1,2}\]\([^)\s]*\)|\*\*\d+(?::\d\d){1,2}\*\*)[ \t]*")
PICTURES = (".jpg", ".jpeg", ".png", ".webp")
INK = "#000000"
HL_HEX = {"yellow": "#ffd43b", "green": "#8ce99a", "blue": "#74c0fc", "pink": "#faa2c1", "purple": "#b197fc"}
# Each of Daf's pens, as perfect-freehand's thinning, smoothing and streamline (pens.js's FEEL), for Ink to draw them by
FEEL = {"fountain": (0.6, 0.5, 0.5), "pen": (0.18, 0.6, 0.5), "pencil": (0.45, 0.5, 0.45), "brush": (0.85, 0.7, 0.55),
        "marker": (0, 0.6, 0.5), "highlighter": (0, 0.6, 0.6), "calligraphy": (0.5, 0.5, 0.5)}

_write_lock = threading.RLock()


def _h(text):
    return hashlib.sha1((text or "").strip().encode()).hexdigest()[:16]


def _fh(text):
    return hashlib.sha1((text or "").encode()).hexdigest()


def _short(mid):
    return hashlib.sha1(mid.encode()).hexdigest()[:8]


def _num(v):
    """A number as JavaScript prints it (Ink writes its SVGs from JavaScript)."""
    v = round(v, 4)
    return str(int(v)) if v == int(v) else repr(v)


# ---- which notes -------------------------------------------------------------------------------

def note_of(conn, item):
    """The item's own note in the vault (relative path), if it has one yet."""
    kind, ref = item.split(":", 1)
    if kind == "manga":
        r = conn.execute("SELECT v FROM kv WHERE k = ?", ("sketch_note:" + item,)).fetchone()
        rel = r["v"] if r else None
    else:
        r = conn.execute("SELECT vault_path FROM books WHERE id = ?", (ref,)).fetchone()
        rel = r["vault_path"] if r else None
    return rel if rel and (config.VAULT / rel).is_file() else None


def sketch_of(conn, item):
    """The item's Sketchbook note (relative path), once there is one."""
    r = conn.execute("SELECT path FROM sketch_notes WHERE item = ?", (item,)).fetchone()
    return r["path"] if r and (config.VAULT / r["path"]).is_file() else None


def _make_note(conn, settings, item):
    """A note for an item that has none: as Daf makes one for a highlight. None when it mustn't have one."""
    from . import vaultnotes
    kind, ref = item.split(":", 1)
    if kind == "book":
        b = conn.execute("SELECT private FROM books WHERE id = ?", (ref,)).fetchone()
        if not b or b["private"]:
            return None
        vaultnotes.write_book(conn, settings, ref, create=True)
    elif kind == "doc":
        vaultnotes.write_article(conn, settings, ref)
    else:
        return _manga_note(conn, settings, ref, make=True)
    return note_of(conn, item)


def _norm(t):
    t = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", str(t or "")).lower()
    t = re.sub(r"^(the|a)\s+", "", t)
    return re.sub(r"[^0-9a-z֐-׿぀-ヿ一-鿿]+", "", t)


def _frontmatter(text):
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    out = {}
    for line in text[4:end if end > 0 else 0].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


def _manga_note(conn, settings, series_id, make=False):
    """The note for a manga series: manga-sync's (a note with `type: manga`, matched by the MAL id it
    knows for the series' folder, else by title), else the one Daf made for it. Kept in kv once found."""
    from . import manga
    item = "manga:" + series_id
    try:
        s = manga.library()["series"].get(series_id)
    except Exception:  # noqa: BLE001 - Komga away: the note Daf knows, if any
        s = None
    if not s:
        return note_of(conn, item)
    folder = s.get("folder") or s["name"]
    names = {s["name"], folder, manga.display(folder)}
    try:
        tm = json.loads((manga.CONF.parent / "track-map.json").read_text(encoding="utf-8")).get(folder) or {}
        names |= {tm.get("mangadexTitle"), tm.get("searchTitle")}
    except (OSError, ValueError):
        pass
    mal = None
    try:                                   # manga-sync's own cache of the series' MAL ids (read only)
        mal = json.loads((config.VAULT / ".claude" / "state" / "manga-sync.json").read_text(encoding="utf-8")).get("mal_ids", {}).get(folder)
    except (OSError, ValueError):
        pass
    want = {_norm(n) for n in names if n} - {""}
    found = None
    for p in sorted(config.VAULT.rglob("*.md")):
        if any(part.startswith(".") for part in p.relative_to(config.VAULT).parts) or "sync-conflict" in p.name:
            continue
        try:
            with p.open(encoding="utf-8") as f:
                head = f.read(3000)
        except (OSError, UnicodeDecodeError):
            continue
        if "type: manga" not in head:
            continue
        fm = _frontmatter(head)
        if fm.get("type") != "manga":
            continue
        rel = str(p.relative_to(config.VAULT))
        if mal and str(fm.get("id")) == str(mal):
            found = rel
            break
        if found is None and (want & {_norm(fm.get("title")), _norm(fm.get("englishTitle"))}):
            found = rel
    if not found:
        own = note_of(conn, item)
        if own or not make:
            return own
        found = _daf_manga_note(settings, s)
    conn.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", ("sketch_note:" + item, found))
    return found


def _daf_manga_note(settings, s):
    """A series with no note: one of Daf's, without `type: manga`, so manga-sync never takes it for its own."""
    from . import vaultnotes
    (config.VAULT / "Reference" / "manga").mkdir(parents=True, exist_ok=True)
    rel = f"Reference/manga/{vaultnotes._clip_name('🍙 ' + s['name'])} (Daf).md"
    if not (config.VAULT / rel).exists():
        (config.VAULT / rel).write_text(
            "---\n" f"title: {vaultnotes._yaml(s['name'])}\n" f"daf: {vaultnotes._yaml(config.public_url(settings) + '/#manga/' + s['id'])}\n"
            "tags:\n  - manga\ndatasource: daf\n---\n" f"# {s['name']}\n\n", encoding="utf-8")
    return rel


def _daf_link(settings, item):
    kind, ref = item.split(":", 1)
    from urllib.parse import quote
    return config.public_url(settings) + "/#" + {"book": "ebook", "doc": "read", "manga": "manga"}[kind] + "/" + quote(ref, safe="")


# ---- writing ----------------------------------------------------------------------------------------

def write(conn, settings, item, create=True):
    """The item's Sketchbook note, its Ink blocks and pictures, and the embed in the item's note, as
    the Sketchbook has them now, after taking in what was changed in Obsidian. Returns what happened."""
    with _write_lock:
        own = note_of(conn, item)
        if item.startswith("manga:") and (not own or "(Daf)" in own):
            own = _manga_note(conn, settings, item[6:], make=create and SB.has(conn, item)) or own
        row = conn.execute("SELECT path, hash, base FROM sketch_notes WHERE item = ?", (item,)).fetchone()
        if not own and not row:
            if not create or not SB.has(conn, item):
                return "no note"
            own = _make_note(conn, settings, item)
            if not own:
                return "no note"
        rel = row["path"] if row else _sketch_path(own)
        path = config.VAULT / rel
        before = path.read_text(encoding="utf-8") if path.is_file() else None
        base = json.loads(row["base"]) if row and row["base"] else {}
        took = 0
        if before is not None and (not row or row["hash"] != _fh(before)):
            took = pull(conn, item, before, base)            # edited in Obsidian since: its changes first
        if not SB.has(conn, item) and before is None:
            return "nothing to write"
        body, base2 = _body(conn, settings, item, rel)
        head = _head(before) or _new_head(settings, item, own)
        new = head + body
        now = path.read_text(encoding="utf-8") if path.is_file() else None
        if now != before:                                    # changed while Daf was at it: next time
            later(item)
            return "busy"
        if new != before:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.daf-tmp")
            tmp.write_text(new, encoding="utf-8")
            tmp.replace(path)
        conn.execute("INSERT OR REPLACE INTO sketch_notes (item, path, hash, base) VALUES (?, ?, ?, ?)",
                     (item, rel, _fh(new), json.dumps(base2, ensure_ascii=False)))
        if own:
            _embed_in(own, rel)
        return ("written" if new != before else "unchanged") + (f", {took} from Obsidian" if took else "")


def _sketch_path(own):
    p = config.VAULT / own
    return str((p.parent / (p.stem + SUFFIX + ".md")).relative_to(config.VAULT))


def _head(text):
    """A note's front matter, as it is (the note's own once written)."""
    if text and text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end > 0:
            return text[:end + 5]
    return None


def _new_head(settings, item, own):
    from . import vaultnotes
    back = f'"[[{own[:-3]}]]"' if own else '""'
    return (f"---\nsketchbook: {back}\ndaf: {vaultnotes._yaml(_daf_link(settings, item))}\n"
            "tags:\n  - sketchbook\ndatasource: daf\n---\n")


def _embed_in(own, rel):
    """The Sketchbook embedded in the item's note: Daf's region there, after its other one."""
    p = config.VAULT / own
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return
    region = f"{START}\n## Sketchbook\n\n![[{rel[:-3]}]]\n{END}\n"
    m = REGION.search(text)
    if m:
        new = text[:m.start()] + region + text[m.end():]
    elif DAF_END in text:
        at = text.index(DAF_END) + len(DAF_END)
        new = text[:at] + "\n\n" + region.rstrip("\n") + text[at:]
    else:
        new = text.rstrip("\n") + "\n\n" + region
    if new != text:
        tmp = p.with_name(f".{p.name}.daf-tmp")
        tmp.write_text(new, encoding="utf-8")
        tmp.replace(p)


def _stamp_link(conn, item):
    """Where a time stamp on a video's page goes: the video at that moment (YouTube), or nowhere."""
    if not item.startswith("doc:"):
        return None
    d = conn.execute("SELECT url, kind FROM docs WHERE id = ?", (item[4:],)).fetchone()
    from . import media
    yt = media.youtube_id(d["url"]) if d and d["kind"] == "video" and d["url"] else None
    return (lambda t: f"https://www.youtube.com/watch?v={yt}&t={int(t)}s") if yt else None


def _stamp(t, link):
    st = SB._stamp(t)
    return f"[{st}]({link(t)})" if link else f"**{st}**"


def _esc(line):
    """A typed line as Markdown that stays a line: one starting with # would be a heading, ![ an embed."""
    return "\\" + line if re.match(r"^\s*(#|!\[)", line) else line


def _unesc(line):
    return line.lstrip()[1:] if re.match(r"^\\(#|!\[)", line.lstrip()) else line


def _heading(t):
    return re.sub(r"[\r\n#]+", " ", t.get("title") or "").strip() or ("General" if not t["tab"] else "A chapter")


def _alt(text, placeholder):
    """Ink's plain-text alt for an embed: one line, nothing that breaks ![…](…) (its formatWritingEmbedAltText)."""
    c = re.sub(r"[\[\]\\|<>]", "", re.sub(r"\s+", " ", text or "")).strip()
    return c or placeholder


def _body(conn, settings, item, rel):
    """The note's body, and what it holds (the merge's copy for next time). Writes the blocks' files."""
    link = _stamp_link(conn, item)
    ts = SB.tabs(conn, item)
    one = len(ts) == 1 and ts[0]["tab"] == ""
    out, base = [""], {}
    for t in ts:
        bl = SB.blocks(SB.marks(conn, item, t["tab"]))
        if not one:
            out += [f"### {_heading(t)}", ""]
        seen = base.setdefault(t["tab"], [])
        for b in bl:
            if b["kind"] == "text":
                body = "\n".join(_esc(x) for x in (b.get("text") or "").split("\n")).strip()
                if b.get("t") is not None:
                    body = (_stamp(b["t"], link) + " " + body).strip()
                out += [body + f" ^daf-t{_short(b['id'])}", ""]
                seen.append([b["id"], "text", _h(b.get("text"))])
            elif b["kind"] == "ink":
                f = _ink_file(conn, item, b, rel)
                if b.get("t") is not None:
                    out += [_stamp(b["t"], link), ""]
                out += [_ink_line(b, f), ""]
                seen.append([b["id"], "ink", f["path"]])
            elif b["kind"] == "image":
                pic = _picture_file(conn, item, b, rel)
                if not pic:
                    continue
                out += [f"![[{pic}]]", ""]
                if b["strokes"]:
                    f = _ink_file(conn, item, dict(b, type="drawing", vb=[0, 0, SB.INK_W, b["h"]]), rel, over=True)
                    out += [_ink_line(dict(b, type="drawing", vb=[0, 0, SB.INK_W, b["h"]], transcript=None), f), ""]
                seen.append([b["id"], "image", pic])
    return "\n".join(out).rstrip("\n") + "\n", base


def _ink_line(b, f):
    """An Ink block's embed, as Ink writes it (build-embeds.ts): the picture with its transcript, and the Edit link."""
    if b["type"] == "writing":
        q = urlencode({"aspectRatio": f"{SB.INK_W / f['h']:.3f}"})
        return f" ![{_alt(b.get('transcript'), 'InkWriting')}](<{f['path']}>) [Edit Writing]({EDIT}?type=inkWriting&{q})"
    vb = b.get("vb") or f["vb"]
    q = urlencode({"width": "500", "aspectRatio": f"{vb[2] / vb[3]:.3f}", "viewBoxX": _num(vb[0]), "viewBoxY": _num(vb[1]),
                   "viewBoxW": _num(vb[2]), "viewBoxH": _num(vb[3])})
    return f" ![{_alt(b.get('transcript'), 'InkDrawing')}](<{f['path']}>) [Edit Drawing]({EDIT}?type=inkDrawing&{q})"


def _media_path(rel, key, ext):
    p = config.VAULT / rel
    return str((p.parent / MEDIA / f"{p.stem} · {_short(key)}{ext}").relative_to(config.VAULT))


def _picture_file(conn, item, b, rel):
    """A picture's file beside the note (copied from Daf's once), by its vault path."""
    r = conn.execute("SELECT path FROM sketch_files WHERE blk = ? AND path NOT LIKE '%.svg'", (b["id"],)).fetchone()
    src = SB.image_path(b["file"])
    dest = r["path"] if r else _media_path(rel, b["id"], src.suffix if src.suffix != ".jpeg" else ".jpg")
    p = config.VAULT / dest
    if not p.exists():
        if not src.exists():
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, p)
    if not r:
        conn.execute("INSERT OR REPLACE INTO sketch_files (path, item, blk, hash, ids) VALUES (?, ?, ?, NULL, NULL)", (dest, item, b["id"]))
    return dest


# ---- Ink's SVG files ------------------------------------------------------------------------------------

def _pen_ease(t):
    return t * 0.65 + math.sin(t * math.pi / 2) * 0.35        # Ink's penStrokePressureEasing


def _style(s):
    th, sm, st = FEEL.get(s["tool"], FEEL["pen"])
    if s["tool"] == "highlighter":
        color = HL_HEX.get(s["color"], "#ffd43b") + f"{round(s.get('o', 0.5) * 255):02x}"
    else:
        color = "currentColor" if s["color"] == "ink" else s["color"]
    return {"size": s["size"], "thinning": th, "smoothing": sm, "streamline": st, "simulatePressure": False,
            "inputKind": "pen", "color": color, "captureZoom": 1}


def _outline(s):
    th, sm, st = FEEL.get(s["tool"], FEEL["pen"])
    hl = s["tool"] == "highlighter"
    return freehand.get_stroke(s["pts"], size=s["size"], thinning=th, smoothing=sm, streamline=st, simulate=False,
                               easing=_pen_ease, last=True, start={"cap": not hl}, end={"cap": not hl})


def ink_svg(b, strokes):
    """An Ink file for a block: what shows (its ruled lines and strokes) and what Ink reads (its metadata).
    Returns (the SVG, its height, its viewBox)."""
    writing = b["type"] == "writing"
    paths, maxy, box = [], 0.0, [math.inf, math.inf, -math.inf, -math.inf]
    for s in strokes:
        o = _outline(s)
        if not o:
            continue
        for x, y in o:
            box = [min(box[0], x), min(box[1], y), max(box[2], x), max(box[3], y)]
        maxy = max(maxy, box[3])
        d = freehand.svg_path(o)
        if s["tool"] == "highlighter":
            paths.append(f'<path d="{d}" fill="{HL_HEX.get(s["color"], "#ffd43b")}" fill-opacity="{s.get("o", 0.5)}" class="ink-type-stroke" />\n')
        elif s["color"] == "ink":
            paths.append(f'<path d="{d}" fill="{INK}" class="ink-type-stroke ink-color-primary" />\n')
        else:
            paths.append(f'<path d="{d}" fill="{s["color"]}" class="ink-type-stroke" />\n')
    snap = {"version": 1, "strokes": [{"id": s["id"], "points": s["pts"], "style": _style(s), "offset": {"x": 0, "y": 0}} for s in strokes],
            "gridEnabled": False}
    lines = ""
    if writing:
        snap["writingLineHeight"] = SB.LINE
        h = 2.5 * SB.LINE
        if strokes:
            h = max((math.ceil(maxy / SB.LINE) + 0.5) * SB.LINE, h)
        margin = SB.INK_W * 0.05
        for i in range(1, int(h // SB.LINE) + 1):
            lines += (f'<line x1="{_num(margin)}" y1="{_num(i * SB.LINE)}" x2="{_num(SB.INK_W - margin)}" y2="{_num(i * SB.LINE)}" '
                      'stroke="#888888" stroke-opacity="0.3" class="ink-type-writing-line ink-color-writing-line" />\n')
        vb = [0, 0, SB.INK_W, h]
    elif b.get("vb"):
        vb = b["vb"]
    elif strokes and box[0] < math.inf:
        vb = [box[0] - 16, box[1] - 16, box[2] - box[0] + 32, box[3] - box[1] + 32]
    else:
        vb = [0, 0, 1, 1]
    ink = f'<ink plugin-version="{INK_PLUGIN}" file-type="{"inkWriting" if writing else "inkDrawing"}"' + (f' writing-line-height="{SB.LINE}"' if writing else "") + "/>"
    meta = ["<metadata>", ink]
    if b.get("transcript"):
        meta.append(f"<transcript>{_x(b['transcript'])}</transcript>")
    meta += [f'<ink-canvas version="{INK_CANVAS}">{_x(json.dumps(snap, separators=(",", ":"), ensure_ascii=False))}</ink-canvas>', "</metadata>"]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(_num(v) for v in vb)}">\n' + "\n".join(meta) + "\n" + lines + "".join(paths) + "</svg>\n"
    return svg, vb[3], vb


def _x(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_ink(text):
    """An Ink file's type, strokes (offsets applied), transcript and viewBox; None when it isn't one Daf can read."""
    m = re.search(r"<ink-canvas\b[^>]*>([\s\S]*?)</ink-canvas>", text or "")
    if not m:
        return None
    try:
        snap = json.loads(html.unescape(m.group(1)))
    except ValueError:
        return None
    ft = re.search(r'file-type\s*=\s*["\'](inkWriting|inkDrawing)["\']', text)
    tr = re.search(r"<transcript>([\s\S]*?)</transcript>", text)
    vb = re.search(r'<svg\b[^>]*viewBox="([^"]+)"', text)
    strokes = []
    for s in snap.get("strokes") or []:
        try:
            off = s.get("offset") or {}
            ox, oy = float(off.get("x") or 0), float(off.get("y") or 0)
            pts = [[round(float(p[0]) + ox, 1), round(float(p[1]) + oy, 1), round(float(p[2]) if len(p) > 2 else 0.5, 2)] for p in s.get("points") or []]
        except (TypeError, ValueError, IndexError):
            continue
        if pts:
            strokes.append({"id": str(s.get("id") or ""), "pts": pts, "style": s.get("style") or {}})
    try:
        box = [float(v) for v in vb.group(1).split()] if vb else None
    except ValueError:
        box = None
    return {"type": "drawing" if ft and ft.group(1) == "inkDrawing" else "writing", "strokes": strokes,
            "transcript": html.unescape(tr.group(1)).strip() if tr else None, "vb": box if box and len(box) == 4 else None}


def _from_ink(s, blk, old=None):
    """A stroke from an Ink file as a Daf stroke (one Daf had keeps its pen and colour, its points the file's)."""
    st = s["style"]
    if old:
        return dict(old, pts=s["pts"], blk=blk)
    color, tool = str(st.get("color") or ""), "fountain"
    m = re.fullmatch(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", color)
    if m and m.group(2) and int(m.group(2), 16) < 250:
        hexc = "#" + m.group(1).lower()
        tool, color = "highlighter", next((k for k, v in HL_HEX.items() if v == hexc), "yellow")
    elif m and color.lower() not in ("#000000", "#1e1e1e"):
        color = "#" + m.group(1).lower()
    else:
        color = "ink"
    return {"id": _stroke_id(blk, s["id"]), "kind": "stroke", "blk": blk, "tool": tool, "color": color,
            "size": max(0.3, float(st.get("size") or 6)), "o": 0.5 if tool == "highlighter" else 1, "pts": s["pts"]}


def _stroke_id(blk, ink_id):
    return ink_id if SB.MARK_ID.match(ink_id or "") and ink_id.startswith("k") else "k" + hashlib.sha1(f"{blk}|{ink_id}".encode()).hexdigest()[:20]


def _ink_file(conn, item, b, rel, over=False):
    """An ink block's SVG beside the note (or a picture's drawing over it), merged first with what Ink
    changed in it since Daf wrote it. Returns {path, h, vb}."""
    key = b["id"] + (":over" if over else "")
    r = conn.execute("SELECT path, hash, ids FROM sketch_files WHERE blk = ? AND path LIKE '%.svg'", (b["id"],)).fetchone()
    path = r["path"] if r else (b.get("file") if b["kind"] == "ink" and b.get("file") else _media_path(rel, key, ".svg"))
    p = config.VAULT / path
    prev = p.read_text(encoding="utf-8") if p.is_file() else None
    strokes = b["strokes"]
    if prev is not None and (not r or r["hash"] != _fh(prev)):
        strokes = _merge_ink(conn, item, b, prev, json.loads(r["ids"]) if r and r["ids"] else None)
    svg, h, vb = ink_svg(b, strokes)
    if svg != prev:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.daf-tmp")
        tmp.write_text(svg, encoding="utf-8")
        tmp.replace(p)
    conn.execute("INSERT OR REPLACE INTO sketch_files (path, item, blk, hash, ids) VALUES (?, ?, ?, ?, ?)",
                 (path, item, b["id"], _fh(svg), json.dumps([s["id"] for s in strokes])))
    return {"path": path, "h": h, "vb": vb}


def _merge_ink(conn, item, b, text, had):
    """An Ink file changed since Daf wrote it: its strokes into the block. Written or moved in Ink: taken;
    erased in Ink (it was there when Daf wrote it): gone; written in Daf since: kept."""
    got = read_ink(text)
    if not got:
        return b["strokes"]
    tab = conn.execute("SELECT tab FROM sketch_marks WHERE id = ?", (b["id"],)).fetchone()
    tab = tab["tab"] if tab else ""
    ours = {s["id"]: s for s in b["strokes"]}
    had = set(had) if had is not None else set(ours)
    theirs = {}
    for s in got["strokes"]:
        sid = _stroke_id(b["id"], s["id"])
        theirs[sid] = _from_ink(s, b["id"], ours.get(sid))
    add = [s for sid, s in theirs.items() if sid not in ours and sid not in had or (sid in ours and s["pts"] != ours[sid]["pts"])]
    gone = [sid for sid in ours if sid in had and sid not in theirs]
    if add or gone:
        SB.change(conn, item, tab, [dict(s, kind="stroke") for s in add], gone)
    kept = [s for sid, s in ours.items() if sid not in gone]
    kept = [theirs.get(s["id"], s) for s in kept] + [s for s in add if s["id"] not in ours]
    return kept


# ---- Obsidian's edits back ----------------------------------------------------------------------------

def _parse(text):
    """The note's blocks under each heading: {heading or None: [(kind, key, value)]}, in order. kind:
    text (key: its short id or None), ink (key: its path; value: (type, transcript, embed URL)), image (key: its path)."""
    body = text
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        body = text[end + 5:] if end > 0 else text
    sections, para = {None: []}, []
    cur = sections[None]

    def flush(sid=None):
        b = "\n".join(_unesc(x) for x in para).strip()
        if sid:
            b = STAMP.sub("", b, count=1).strip()
        if sid or (b and not STAMP.fullmatch(b)):
            cur.append(("text", sid, b))
        para.clear()

    for line in body.splitlines():
        if line.startswith("### "):
            flush()
            cur = sections.setdefault(line[4:].strip(), [])
            continue
        if line.startswith("#"):
            flush()
            continue
        m = INK_LINE.match(line)
        if m:
            flush()
            cur.append(("ink", m.group(2), ("writing" if m.group(3) == "Writing" else "drawing", m.group(1), m.group(4))))
            continue
        m = PIC_LINE.match(line.strip())
        if m:
            flush()
            cur.append(("image", (m.group(1) or m.group(2) or "").strip(), None))
            continue
        t = TEXT_ID.search(line)
        if t:
            para.append(line[:t.start()])
            flush(t.group(1))
            continue
        if not line.strip():
            flush()
            continue
        para.append(line)
    flush()
    return {k: v for k, v in sections.items() if v}


def _resolve(path):
    """A link in the note to a file in the vault (a full path, or a name Obsidian would find)."""
    path = path.strip()
    if (config.VAULT / path).is_file():
        return path
    name = path.split("/")[-1]
    for p in config.VAULT.rglob(name):
        if not any(part.startswith(".") for part in p.relative_to(config.VAULT).parts):
            return str(p.relative_to(config.VAULT))
    return None


def pull(conn, item, text, base):
    """The note changed since Daf wrote it: what changed there, into the Sketchbook, block by block
    (against what it held then: base). Returns how many blocks changed."""
    parsed = _parse(text)
    tabs = {t["tab"]: t for t in conn.execute("SELECT tab, title FROM sketch_tabs WHERE item = ?", (item,)).fetchall()}
    by_title = {}
    for k, t in tabs.items():
        by_title.setdefault(_heading(dict(t)), k)
    # what's anywhere in the note (a paragraph moved under another heading isn't gone)
    texts = {_short(r["id"]): (r["tab"], r["id"]) for r in conn.execute("SELECT id, tab FROM sketch_marks WHERE item = ? AND kind = 'text'", (item,))}
    files = {r["path"]: r["blk"] for r in conn.execute("SELECT path, blk FROM sketch_files WHERE item = ?", (item,))}
    present = set()
    for entries in parsed.values():
        for kind, key, _v in entries:
            if kind == "text" and key in texts:
                present.add(texts[key][1])
            elif kind != "text":
                rel = _resolve(key)
                if rel in files:
                    present.add(files[rel])
    took, now, done = 0, int(time.time()), set()
    for head, entries in parsed.items():
        if head is None or head == "General":
            tab, extra = "", None
        elif head in by_title:
            tab, extra = by_title[head], None
        else:
            tab, extra = "", head            # a heading of his: what's under it goes to General, the heading as text
        took += _pull_tab(conn, item, tab, entries, base.get(tab, []), extra, now, texts, files, present)
        done.add(tab)
    for tab, was in base.items():          # a tab whose heading is gone from the note
        if tab not in done:
            took += _pull_tab(conn, item, tab, [], was, None, now, texts, files, present)
    return took


def _pull_tab(conn, item, tab, entries, was, extra, now, texts, files, present):
    ours = SB.blocks(SB.marks(conn, item, tab))
    by_id = {b["id"]: b for b in ours}
    base = {x[0]: x for x in was}
    add, remove, order, took = [], [], [], 0
    if extra:
        entries = [("text", None, extra)] + entries
    for kind, key, val in entries:
        if kind == "text" and key:
            where = texts.get(key)
            if not where:
                continue                                   # deleted in Daf since: it goes
            bid = where[1]
            b = by_id.get(bid)
            if not b:                                      # moved here from another heading
                r = conn.execute("SELECT data FROM sketch_marks WHERE id = ?", (bid,)).fetchone()
                b = dict(json.loads(r["data"]), id=bid, kind="text")
                add.append(dict(b, text=val))
                order.append(bid)
                took += 1
                continue
            if val != (b.get("text") or "").strip() and (bid not in base or _h(val) != base[bid][2]):
                add.append({k: v for k, v in b.items() if k not in ("strokes", "updated")} | {"text": val})
                took += 1
            order.append(bid)
        elif kind == "text" and val:
            bid = "t" + hashlib.sha1(f"{item}|{tab}|{val}|{len(order)}".encode()).hexdigest()[:20]
            add.append({"id": bid, "kind": "text", "text": val, "ord": 0})
            order.append(bid)
            took += 1
        elif kind in ("ink", "image"):
            rel = _resolve(key)
            bid = files.get(rel) if rel else None
            if bid:
                if bid in by_id:
                    order.append(bid)
                continue                                   # deleted in Daf since, or on another tab's page
            if rel and kind == "ink":
                got = read_ink((config.VAULT / rel).read_text(encoding="utf-8"))
                if not got:
                    continue
                bid = "b" + hashlib.sha1(f"{item}|{rel}".encode()).hexdigest()[:20]
                vb = got["vb"]
                q = parse_qs(urlparse(val[2]).query)
                if val[0] == "drawing" and all(k in q for k in ("viewBoxX", "viewBoxY", "viewBoxW", "viewBoxH")):
                    try:
                        vb = [float(q[k][0]) for k in ("viewBoxX", "viewBoxY", "viewBoxW", "viewBoxH")]
                    except ValueError:
                        pass
                blk = {"id": bid, "kind": "ink", "type": got["type"], "ord": 0, "file": rel,
                       "transcript": got["transcript"] or (val[1] if val[1] not in ("InkWriting", "InkDrawing") else None)}
                if got["type"] == "drawing" and vb:
                    blk["vb"] = vb
                add.append(blk)
                add += [_from_ink(s, bid) for s in got["strokes"]]
                conn.execute("INSERT OR REPLACE INTO sketch_files (path, item, blk, hash, ids) VALUES (?, ?, ?, NULL, NULL)", (rel, item, bid))
                files[rel] = bid
                order.append(bid)
                took += 1
            elif rel and kind == "image" and rel.lower().endswith(PICTURES):
                data = (config.VAULT / rel).read_bytes()
                ext = ".jpg" if rel.lower().endswith((".jpg", ".jpeg")) else "." + rel.rsplit(".", 1)[-1].lower()
                name = hashlib.sha1(data).hexdigest() + ext
                SB.IMAGES.mkdir(parents=True, exist_ok=True)
                if not (SB.IMAGES / name).exists():
                    (SB.IMAGES / name).write_bytes(data)
                bid = "i" + hashlib.sha1(f"{item}|{rel}".encode()).hexdigest()[:20]
                add.append({"id": bid, "kind": "image", "ord": 0, "file": name, "h": _picture_h(SB.IMAGES / name)})
                conn.execute("INSERT OR REPLACE INTO sketch_files (path, item, blk, hash, ids) VALUES (?, ?, ?, NULL, NULL)", (rel, item, bid))
                files[rel] = bid
                order.append(bid)
                took += 1
    # what the note had then and hasn't now anywhere was deleted there (unless Daf changed it since)
    for bid, kind, sig in was:
        b = by_id.get(bid)
        if b and bid not in present and bid not in order and (kind != "text" or _h(b.get("text")) == sig):
            remove.append(bid)
            took += 1
    # the order: the note's; what Daf added since (or what's elsewhere in the note) goes after what it followed
    gone = set(remove)
    final = [x for x in order if x not in gone]
    for i, b in enumerate(ours):
        if b["id"] in final or b["id"] in gone or (b["id"] in base and b["id"] not in present):
            continue
        if b["id"] in present and b["id"] not in order:
            continue                                       # moved under another heading
        prev = next((ours[j]["id"] for j in range(i - 1, -1, -1) if ours[j]["id"] in final), None)
        final.insert(final.index(prev) + 1 if prev else 0, b["id"])
    news = {a["id"]: a for a in add if a["kind"] != "stroke"}
    for n, bid in enumerate(final):
        if bid in news:
            news[bid]["ord"] = n + 1
        elif bid in by_id and by_id[bid].get("ord") != n + 1:
            b = by_id[bid]
            add.append({k: v for k, v in b.items() if k not in ("strokes", "updated")} | {"ord": n + 1})
    if add or remove:
        SB.change(conn, item, tab, add, remove, at=now)
    return took


def _picture_h(p):
    """A picture's height at INK_W across."""
    try:
        from PIL import Image
        with Image.open(p) as im:
            return round(SB.INK_W * im.height / im.width, 1)
    except Exception:  # noqa: BLE001
        return SB.INK_W * 0.75


# ---- when ----------------------------------------------------------------------------------------------

_lock = threading.Lock()
_timers = {}
_pulled = {}


def later(item, quiet=6.0, most=45.0):
    """The vault, once the pen has rested a few seconds (and at least every 45 while it hasn't)."""
    now = time.time()
    with _lock:
        t, first = _timers.get(item, (None, now))
        if t:
            t.cancel()
        t = threading.Timer(max(0.5, min(quiet, first + most - now)), _run, (item,))
        t.daemon = True
        _timers[item] = (t, first)
        t.start()


def _run(item):
    with _lock:
        _timers.pop(item, None)
    from . import db
    try:
        with db.session() as conn:
            write(conn, config.load_settings(), item)
    except Exception:  # noqa: BLE001 - the vault is a copy; the next change tries again
        log.exception("sketchbook to the vault: %s", item)


def pull_soon(conn, settings, item, every=30):
    """Before the page shows an item: what was changed in Obsidian, taken in (at most every 30 s an item)."""
    if time.time() - _pulled.get(item, 0) < every:
        return
    _pulled[item] = time.time()
    r = conn.execute("SELECT path, hash FROM sketch_notes WHERE item = ?", (item,)).fetchone()
    if not r:
        return
    try:
        p = config.VAULT / r["path"]
        changed = p.is_file() and _fh(p.read_text(encoding="utf-8")) != r["hash"]
        files = conn.execute("SELECT path, hash FROM sketch_files WHERE item = ? AND hash IS NOT NULL", (item,)).fetchall()
        changed = changed or any((config.VAULT / f["path"]).is_file() and _fh((config.VAULT / f["path"]).read_text(encoding="utf-8")) != f["hash"] for f in files)
        if changed:
            write(conn, settings, item, create=False)
    except Exception:  # noqa: BLE001
        log.exception("sketchbook from the vault: %s", item)
