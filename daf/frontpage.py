"""The Edition's front page on the Kindle: the book's first page, where every headline is a link to its
piece, and the cover, a picture of that front page drawn the way a paper's is (the name, the dateline, a
photograph, the lead and the other headlines), which the Kindle's library shows for the book.

kindlesend.make_epub calls a Paper once it knows which pieces made it into the book (front=Paper(...)):
it gets each piece's chapter and the book's images, and gives back the page and the cover. The cover is
greyscale at the Kindle's own size, 1264 × 1680. Its type is Daf's own (Newsreader, Literata, Frank Ruhl
Libre from web/fonts), with FreeSerif for anything they don't have.
"""
import html as H
import io
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("daf.frontpage")

W, HGT, M = 1264, 1680, 56                    # the Paperwhite's screen, and the margin
FONTS = Path(__file__).resolve().parent.parent / "web" / "fonts"
FALLBACK = [Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf")]
FALLBACK_BOLD = [Path("/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf")]
HEBREW = re.compile(r"[֐-׿יִ-ﭏ]")
POINTS = re.compile(r"[֑-ׇ]")          # vowel points and cantillation: the cover's dateline goes without them
INK, GREY, RULE = 0, 85, 40


# ---- type -----------------------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _font(name, size, weight=None):
    """A font from web/fonts (a variable one set to `weight`), else the fallback, else Pillow's own."""
    from PIL import ImageFont
    for p in ([FONTS / name] if name else []) + (FALLBACK_BOLD if (weight or 400) >= 600 else FALLBACK):
        if not p.is_file():
            continue
        try:
            f = ImageFont.truetype(str(p), size)
        except OSError:
            continue
        if weight and p.parent == FONTS:
            try:
                axes = f.get_variation_axes()
                vals = []
                for a in axes:
                    tag = (a.get("name") or b"").decode() if isinstance(a.get("name"), bytes) else str(a.get("name") or "")
                    if tag.lower().startswith("weight") or tag == "wght":
                        vals.append(max(a["minimum"], min(a["maximum"], weight)))
                    elif tag.lower().startswith("optical") or tag == "opsz":
                        vals.append(max(a["minimum"], min(a["maximum"], size * 0.75)))
                    else:
                        vals.append(a.get("default", a["minimum"]))
                f.set_variation_by_axes(vals)
            except (OSError, AttributeError, KeyError):
                pass                        # not a variable font: its own weight
        return f
    return ImageFont.load_default(size)


def _fallback(size, weight):
    return _font("", size, weight)


@lru_cache(maxsize=4096)
def _has(font, ch):
    """Whether a font draws this character, rather than its "missing" box."""
    if ch.isspace():
        return True
    try:
        return _ink(font, ch) != _ink(font, "\ue000")       # a private-use character: no font has it
    except Exception:  # noqa: BLE001
        return False


@lru_cache(maxsize=4096)
def _ink(font, ch):
    from PIL import Image, ImageDraw
    im = Image.new("L", (round(font.size) * 2, round(font.size) * 2))
    ImageDraw.Draw(im).text((0, 0), ch, font=font, fill=255)
    return im.tobytes()


class Face:
    """One style of type: a Daf font with a fallback for the characters it lacks, and Hebrew set right to left."""

    def __init__(self, name, size, weight=None, hebrew="frank-ruhl-libre-hebrew-wght-normal.woff2"):
        self.size, self.weight = size, weight
        self.main = _font(name, size, weight)
        self.alt = _fallback(size, weight)
        self.heb = _font(hebrew, size, weight)

    def _runs(self, text):
        """[(font, text)]: the main font, and the fallback for what it can't draw."""
        out = []
        for ch in text:
            f = self.main if _has(self.main, ch) else self.alt
            if out and out[-1][0] is f:
                out[-1][1].append(ch)
            else:
                out.append((f, [ch]))
        return [(f, "".join(cs)) for f, cs in out]

    def _rtl_font(self, text):
        return self.heb if all(_has(self.heb, ch) for ch in text) else self.alt

    def width(self, d, text):
        if HEBREW.search(text):
            return d.textlength(text, font=self._rtl_font(text), **_rtl())
        return sum(d.textlength(t, font=f) for f, t in self._runs(text))

    def draw(self, d, x, y, text, fill=INK):
        """Text whose line starts at y: set on a baseline at the same depth in every font, since their own
        space above the letters differs (Literata has a lot, Newsreader almost none)."""
        y += round(self.size * 0.84)
        if HEBREW.search(text):
            d.text((x, y), text, font=self._rtl_font(text), fill=fill, anchor="ls", **_rtl())
            return
        for f, t in self._runs(text):
            d.text((x, y), t, font=f, fill=fill, anchor="ls")
            x += d.textlength(t, font=f)

    def line_h(self):
        return round(self.size * 1.18)


def _rtl():
    from PIL import features
    return {"direction": "rtl"} if features.check("raqm") else {}


def _plain(text):
    """Text as the cover sets it: one line of it, quotes and dashes kept."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text or "")).strip()


def wrap(d, face, text, width, most):
    """Lines of text that fit the width, at most `most`, the last cut with an ellipsis if it had to be."""
    words, lines, cur = _plain(text).split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if face.width(d, t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > most:
        lines = lines[:most]
        last = lines[-1]
        while last and face.width(d, last + "…") > width:
            last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
        lines[-1] = last.rstrip(",;:—-– ") + "…"
    return lines


def _block(d, face, lines, x, y, width, fill=INK, gap=0):
    """Draws the lines (Hebrew ones from the right edge); returns the y under them."""
    for ln in lines:
        lx = x + width - face.width(d, ln) if HEBREW.search(ln) else x
        face.draw(d, lx, y, ln, fill)
        y += face.line_h() + gap
    return y


# ---- the picture ----------------------------------------------------------------------------------

def photo_score(data):
    """How much an image is a photograph rather than a logo, a title card or a chart: a photograph spreads
    its greys over most of the range, a flat graphic sits on two or three. 0 for what can't be read, is
    too small, or is a banner's shape."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:  # noqa: BLE001
        return 0.0
    if im.width < 300 or im.height < 160 or not 0.5 <= im.width / im.height <= 2.4:
        return 0.0
    g = im.convert("L").resize((96, 96))
    hist = g.histogram()
    bins = [sum(hist[i:i + 4]) for i in range(0, 256, 4)]          # 64 shades
    n = sum(bins) or 1
    used = sum(1 for b in bins if b > n * 0.004)
    top2 = sum(sorted(bins, reverse=True)[:2]) / n
    return round(used * (1 - top2), 2)


PHOTO = 20                                    # a score at least this is a photograph


def wide(data, width=1200, ratio=0.5):
    """The picture as the front page has it: grey, cut to twice as wide as it's high (so the headlines
    still fit on the first screen), its greys stretched for e-ink. JPEG bytes, or None."""
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        im = ImageOps.autocontrast(ImageOps.fit(im.convert("L"), (width, round(width * ratio)), Image.LANCZOS), cutoff=1)
    except Exception:  # noqa: BLE001
        return None
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82, optimize=True)
    return out.getvalue()


FACE_SHARE = 0.02                             # a face over this share of a picture makes it a portrait


@lru_cache(maxsize=1)
def _faces():
    """OpenCV's frontal-face detector, or None where it isn't there: OpenCV is optional, and OpenCV 5
    dropped the cascades (requirements.txt keeps it below 5). Never raises, so the check can't cost
    the Kindle its copy."""
    try:
        import cv2
        c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        return None if c.empty() else c
    except Exception:  # noqa: BLE001 - no OpenCV, or one without the cascades
        log.info("front page: no face detector, so no face check", exc_info=True)
        return None


def big_face(data):
    """Whether a picture is mostly someone's face (one covering more than FACE_SHARE of it), the kind a
    front page does better without: someone glaring or aiming at the reader first thing in the morning.
    OpenCV's frontal-face cascade, asked for four confirmations (six missed a tilted face), and the face
    has to be found in the mirror image too, which faces are and stray textures mostly aren't. Tried on
    50 pictures from three editions: all five portraits caught, two drawings wrongly (the next picture
    is used then). Always False without OpenCV."""
    det = _faces()
    if det is None:
        return False
    try:
        from PIL import Image
        import numpy as np
        im = Image.open(io.BytesIO(data))
        im.load()
        g = np.array(im.convert("L"))
        h, w = g.shape[:2]

        def found(img):
            got = det.detectMultiScale(img, scaleFactor=1.1, minNeighbors=4, minSize=(max(24, w // 14), max(24, h // 14)))
            return [tuple(int(v) for v in f) for f in got if f[2] * f[3] / float(w * h) > FACE_SHARE]
        here = found(g)
        if not here:
            return False
        for mx, my, mw, mh in found(np.ascontiguousarray(g[:, ::-1])):
            x2 = w - mx - mw                  # where the mirror's face sits in the picture itself
            for x, y, fw, fh in here:
                ix = max(0, min(x + fw, x2 + mw) - max(x, x2))
                iy = max(0, min(y + fh, my + mh) - max(y, my))
                if ix * iy > 0.4 * fw * fh:
                    return True
        return False
    except Exception:  # noqa: BLE001 - a picture the detector can't read isn't a face
        return False


def pick_picture(items, candidates):
    """(item id, image bytes, where it came from) of the first photograph in the paper's order that isn't
    mostly a face, or None (the page goes without one rather than lead with a portrait).
    candidates: {item id: [(key, bytes), …]} with the piece's own pictures, best first."""
    for it in items:
        for key, data in candidates.get(it["id"], []):
            if data and photo_score(data) >= PHOTO and not big_face(data):
                return it["id"], data, key
    return None


# ---- the cover ------------------------------------------------------------------------------------

def _dateline(day, number):
    return f'{day.strftime("%A")}, {day.day} {day.strftime("%B")} {day.year}'.upper(), f"No. {number}" if number else ""


def cover(items, day, number=None, hebrew="", picture=None):
    """The front page as a picture (JPEG bytes, greyscale, 1264 × 1680): the name, the dateline, a
    photograph, the lead with its opening lines, and the other headlines two by two while they fit."""
    from PIL import Image, ImageDraw, ImageOps
    img = Image.new("L", (W, HGT), 255)
    d = ImageDraw.Draw(img)
    inner = W - 2 * M
    y = 34
    mast = Face("newsreader-latin-wght-normal.woff2", 210, 700)
    tw = mast.width(d, "Daf")
    mast.draw(d, (W - tw) / 2, y, "Daf")
    y += 236
    d.rectangle((M, y, W - M, y + 4), fill=INK)
    d.rectangle((M, y + 9, W - M, y + 10), fill=INK)
    y += 22
    small = Face("literata-latin-wght-normal.woff2", 25, 500)
    date, no = _dateline(day, number)
    small.draw(d, (W - small.width(d, date)) / 2, y, date)
    if no:
        small.draw(d, M, y, no)
    heb = _plain(POINTS.sub("", hebrew or ""))
    if heb:
        hf = Face("frank-ruhl-libre-latin-wght-normal.woff2", 28, 500)
        hf.draw(d, W - M - hf.width(d, heb), y - 3, heb)
    y += 40
    d.rectangle((M, y, W - M, y + 1), fill=INK)
    y += 26

    if not items:
        return _jpeg(img)
    lead, rest = items[0], items[1:]
    if picture:
        try:
            ph = Image.open(io.BytesIO(picture[1]))
            ph.load()
            ph = ImageOps.autocontrast(ImageOps.fit(ph.convert("L"), (inner, round(inner * 0.5)), Image.LANCZOS), cutoff=1)
            img.paste(ph, (M, y))
            y += ph.height + 10
            if picture[0] != lead["id"]:
                cap = Face("literata-latin-wght-italic.woff2", 21, 400)
                owner = next((it for it in items if it["id"] == picture[0]), None)
                if owner:
                    y = _block(d, cap, wrap(d, cap, owner["title"], inner, 1), M, y, inner, GREY)
            y += 14
        except Exception:  # noqa: BLE001 - a picture that won't draw leaves the page without one
            log.info("front page: the picture didn't draw", exc_info=True)

    kick = Face("literata-latin-wght-normal.woff2", 20, 600)
    hl = Face("newsreader-latin-wght-normal.woff2", 66, 650)
    dek = Face("literata-latin-wght-normal.woff2", 29, 400)
    meta = Face("literata-latin-wght-normal.woff2", 21, 400)
    if lead.get("section") and lead["section"] != "Lead":
        y = _block(d, kick, [lead["section"].upper()], M, y, inner, GREY) + 4
    y = _block(d, hl, wrap(d, hl, lead["title"], inner, 3), M, y, inner, gap=-4) + 10
    if lead.get("summary"):
        y = _block(d, dek, wrap(d, dek, lead["summary"], inner, 3), M, y, inner, gap=2) + 8
    y = _block(d, meta, [_meta(lead)], M, y, inner, GREY) + 20

    # the rest, two by two, a rule between rows, while there's room for a whole row
    col, gut = (inner - 44) // 2, 44
    hl2 = Face("newsreader-latin-wght-normal.woff2", 37, 650)
    kick2 = Face("literata-latin-wght-normal.woff2", 17, 600)
    meta2 = Face("literata-latin-wght-normal.woff2", 18, 400)
    for i in range(0, len(rest), 2):
        row = rest[i:i + 2]
        for most in (3, 2, 1):                  # near the foot, a row's headlines get shorter before it's left out
            blocks = [(it, wrap(d, hl2, it["title"], col, most)) for it in row]
            h = max(kick2.line_h() + 4 + len(lines) * (hl2.line_h() - 3) + meta2.line_h() for _, lines in blocks) + 24
            if y + h <= HGT - 24:
                break
        else:
            break
        d.rectangle((M, y, W - M, y), fill=RULE)
        y += 14
        for n, (it, lines) in enumerate(blocks):
            x = M + n * (col + gut)
            yy = _block(d, kick2, [(it.get("section") or "").upper()], x, y, col, GREY) + 4
            yy = _block(d, hl2, lines, x, yy, col, gap=-3) + 2
            _block(d, meta2, [_meta(it)], x, yy, col, GREY)
        if len(blocks) == 2:
            d.rectangle((M + col + gut // 2, y, M + col + gut // 2, y + h - 22), fill=180)
        y += h - 8
    return _jpeg(img)


def _meta(it):
    mins = it.get("minutes")
    kind = {"video": "video", "podcast": "podcast"}.get(it.get("kind"), "")
    return " · ".join(x for x in (it.get("publication") or it.get("source") or "", kind, f"{mins} min" if mins else "") if x)


def _jpeg(img):
    out = io.BytesIO()
    img.save(out, "JPEG", quality=84, optimize=True)
    return out.getvalue()


# ---- the first page -------------------------------------------------------------------------------

def page(items, day, number=None, hebrew="", href=None, picture_name=None, picture_for=None):
    """The book's first page: the name, the dateline, then every piece with its section, its headline as a
    link to its chapter (href: {id: "cN.xhtml"}; a piece the book hasn't got stays unlinked), and where it's
    from, how long and why it's here. The lead has its opening lines, and the picture stands over its piece."""
    href = href or {}
    no = f"No. {number}" if number else ""
    date = f'{day.strftime("%A")}, {day.day} {day.strftime("%B")} {day.year}'
    line = " · ".join(H.escape(x) for x in (no, date, hebrew) if x)
    out = [f'<p class="mast">Daf</p><p class="dl">{line}</p>']
    for i, it in enumerate(items):
        rtl = bool(HEBREW.search(it.get("title") or ""))
        cls = "st lead" if i == 0 else "st"
        out.append(f'<div class="{cls}"' + (' dir="rtl"' if rtl else "") + ">")
        if picture_name and it["id"] == picture_for:
            out.append(f'<div class="pic"><img src="{H.escape(picture_name, quote=True)}" alt=""/></div>')
        label = " · ".join(x for x in ("" if it.get("section") == "Lead" else it.get("section") or "",
                                       {"video": "video", "podcast": "podcast"}.get(it.get("kind"), "")) if x)
        if label:                                 # the lead goes without one: it's the lead by where it stands
            out.append(f'<p class="k">{H.escape(label)}</p>')
        t = H.escape(it.get("title") or "Untitled")
        link = href.get(it["id"])
        out.append(f'<p class="t"><a href="{link}">{t}</a></p>' if link else f'<p class="t">{t}</p>')
        if i == 0 and it.get("summary"):
            out.append(f'<p class="dek">{H.escape(it["summary"])}</p>')
        m = " · ".join(x for x in (it.get("publication") or it.get("source") or "", f'{it["minutes"]} min' if it.get("minutes") else "", it.get("why") or "") if x)
        out.append(f'<p class="m">{H.escape(m)}</p></div>')
    return "".join(out)


class Paper:
    """The front page and the cover for one edition, made when make_epub calls it: ctx has "href"
    ({id: chapter file}), "images" (the book's kindlesend._Images) and "blocks" ({id: its blocks})."""

    def __init__(self, items, day, number=None, hebrew="", hebrew_he="", thumbs=None):
        self.items, self.day, self.number = items, day, number
        self.hebrew, self.hebrew_he = hebrew, hebrew_he
        self.thumbs = thumbs or {}                # {id: the piece's own thumbnail as bytes}

    def __call__(self, ctx):
        images, blocks = ctx["images"], ctx.get("blocks") or {}
        cands = {}
        for it in self.items:
            if it["id"] not in ctx["href"]:
                continue
            got = []
            for b in blocks.get(it["id"]) or []:
                if b.get("t") == "img" and b.get("src") in images.got and images.got[b["src"]]:
                    got.append((b["src"], images.got[b["src"]][0]))
                    break                         # the first picture in a piece is the one that stands for it
            if self.thumbs.get(it["id"]):
                got.append(("thumb:" + it["id"], self.thumbs[it["id"]]))
            cands[it["id"]] = got
        pic = pick_picture(self.items, cands)
        name = None
        if pic:
            cut = wide(pic[1])
            name = images.put("front:" + pic[0], cut) if cut else None
        xhtml = page(self.items, self.day, self.number, self.hebrew, ctx["href"], name, pic[0] if pic else None)
        try:
            jpg = cover(self.items, self.day, self.number, self.hebrew_he or self.hebrew, pic)
        except Exception:  # noqa: BLE001 - the book goes without a cover rather than not at all
            log.exception("front page cover")
            jpg = None
        return xhtml, jpg
