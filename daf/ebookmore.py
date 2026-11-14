"""Edit book's other tools, as Calibre's own editor has them, on the same working copy as
ebookedit.py (each change after a checkpoint, so Undo and Checkpoints work as for the others):

- Split the HTML file at the cursor, and Merge chosen HTML or CSS files into one: Calibre's
  calibre.ebooks.oeb.polish.split (split and merge), which carry every link and the Table of Contents
  along. Calibre splits before an element, so the split comes before the tag the cursor is in, or the
  first one after it; Daf marks that tag for a moment (data-daf-split) and has Calibre split there.
- Beautify the current file, or all files: calibre.ebooks.oeb.polish.pretty (pretty_all, and for one
  file what pretty_all does to it).
- Insert special character: the character map's categories and favourites (calibre/gui2/tweak_book/
  char_select.py and tprefs' charmap_favorites, Calibre's own lists), with Unicode's names (Python's
  unicodedata, the same names as Calibre's unicode_names) for the search.
- Check external links: the http(s) links Calibre's own check finds (check_external_links: every
  link in the HTML and CSS, by container.iterlinks), fetched by Daf with its rule for the web (public
  addresses only, at every redirect too), a few at a time, with a short timeout.

The split, merge, beautify and finding the links run in calibre-debug through ebookedit's runner,
with their own script (TOOLS_SCRIPT).
"""
import ipaddress
import json
import re
import socket
import threading
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import ebookedit as E

TOOLS_SCRIPT = r'''
def main():
    import json, os, shutil, sys, tempfile, traceback
    job = json.loads(sys.stdin.read())
    work = job["dir"]
    book = os.path.join(work, "book")
    tmp = tempfile.mkdtemp(prefix="tmp-", dir=work)
    out = {"ok": True}
    from calibre.utils.logging import Log
    quiet = Log(level=Log.ERROR)

    def container():
        from calibre.ebooks.oeb.polish.container import get_container
        return get_container(book, log=quiet, tweak_mode=True, tdir=tempfile.mkdtemp(dir=tmp))

    try:
        op = job["op"]
        if op == "split":                       # Calibre's split, before the element Daf marked
            from calibre.ebooks.oeb.polish.split import split
            c = container()
            name = job["name"]
            if c.mime_map.get(name) not in ("application/xhtml+xml", "text/html"):
                raise ValueError("Only an HTML file splits")
            bottom = split(c, name, "//*[@data-daf-split]")
            for n in (name, bottom):            # the mark goes again
                for el in c.parsed(n).xpath("//*[@data-daf-split]"):
                    del el.attrib["data-daf-split"]
                c.dirty(n)
            c.commit()
            out["bottom"] = bottom
        elif op == "merge":                     # Calibre's merge, into the master, in the order given
            from calibre.ebooks.oeb.polish.split import merge
            c = container()
            missing = [n for n in job["names"] if n not in c.name_path_map]
            if missing:
                raise ValueError("No such file: " + missing[0])
            merge(c, job["category"], job["names"], job["master"])
            c.commit()
            out["master"] = job["master"]
        elif op == "pretty":                    # Beautify: all files (pretty_all), or one file as pretty_all does it
            from calibre.ebooks.oeb.base import OEB_DOCS, OEB_STYLES
            from calibre.ebooks.oeb.polish.pretty import pretty_all, pretty_html_tree, pretty_opf, pretty_xml_tree
            from calibre.ebooks.oeb.polish.utils import guess_type
            c = container()
            name = job.get("name")
            if not name:
                pretty_all(c)
            else:
                mt = c.mime_map.get(name)
                if mt in OEB_DOCS:
                    pretty_html_tree(c, c.parsed(name))
                elif mt in OEB_STYLES:
                    c.parsed(name)
                elif name == c.opf_name or mt in {guess_type("a.ncx"), guess_type("a.xml"), guess_type("a.svg")}:
                    root = c.parsed(name)
                    if name == c.opf_name:
                        pretty_opf(root)
                    pretty_xml_tree(root)
                else:
                    raise ValueError("Beautify works on HTML, CSS and XML files")
                c.dirty(name)
            c.commit()
        elif op == "links":                     # the external links, found as Calibre's check_external_links finds them
            from urllib.parse import urlparse
            from calibre.ebooks.oeb.base import OEB_DOCS, OEB_STYLES
            c = container()
            found = {}
            for name, mt in c.mime_map.items():
                if mt in OEB_DOCS or mt in OEB_STYLES:
                    for href, lnum, col in c.iterlinks(name):
                        if urlparse(href).scheme in ("http", "https"):
                            found.setdefault(href, []).append([name, lnum, col])
            out["links"] = [{"href": h, "at": at} for h, at in found.items()]
        else:
            raise ValueError("unknown op " + op)
    except Exception as e:
        out = {"ok": False, "error": str(e) or e.__class__.__name__, "trace": traceback.format_exc()[-1500:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("DAFRESULT " + json.dumps(out))
main()
'''


def _run(cid, job, timeout=900):
    return E._run(cid, job, timeout=timeout, script=TOOLS_SCRIPT)


def _changing(cid, label, fn):
    """A tool that changes the book: a checkpoint first, dropped again if it fails."""
    with E._lock(cid):
        n = E.checkpoint(cid, label)
        try:
            out = fn()
        except Exception:
            E._drop_checkpoint(cid, n)
            raise
        E._changed(cid)
        out["checkpoint"] = n
        return out


# ---------- Split and Merge ----------
_TAG = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<![^>]*>|<\?.*?\?>|</[^>]*>|<([A-Za-z][\w:.-]*)(?:[^>\"']|\"[^\"]*\"|'[^']*')*/?>", re.S)
_NOT_HERE = {"html", "head", "body", "title", "meta", "link", "style", "script", "base"}


def split_point(text, at):
    """Where the mark goes for a split at character `at`: just after the name of the start tag the
    cursor is in, else of the first start tag after it, inside <body>. None when there's none."""
    body = re.search(r"<body\b[^>]*>", text, re.I)
    if not body:
        return None
    at = max(int(at), body.end())
    for m in _TAG.finditer(text, body.end()):
        if m.group(1) is None or m.end() <= at:
            continue
        if m.group(1).split(":")[-1].lower() in _NOT_HERE:
            continue
        return m.end(1)
    return None


def split(cid, name, at):
    """Calibre's split of an HTML file before the element at the cursor (`at`, in characters of the
    file's text). Returns {bottom: the new file's name, checkpoint}."""
    E._need(cid)
    p = E._file(cid, name)
    if not p.is_file():
        raise E.EditError("No such file")
    if not isinstance(at, int) or isinstance(at, bool) or at < 0:
        raise E.EditError("Where to split")

    def go():
        raw = p.read_bytes()
        text, enc = E.decode(raw)
        pos = split_point(text, at)
        if pos is None:
            raise E.EditError("Put the cursor before a tag in the book's text")
        p.write_bytes(E.encode(text[:pos] + ' data-daf-split=""' + text[pos:], enc))
        try:
            return {"bottom": _run(cid, {"op": "split", "name": name})["bottom"]}
        except Exception:
            p.write_bytes(raw)
            raise
    return _changing(cid, "Split " + name.split("/")[-1], go)


def merge(cid, category, names, master):
    """Calibre's merge of chosen HTML files (category text) or CSS files (styles) into the master,
    in the files' order. Returns {master, checkpoint}."""
    E._need(cid)
    if category not in ("text", "styles"):
        raise E.EditError("HTML files or CSS files")
    names = [str(n) for n in names or [] if isinstance(n, str)]
    names = list(dict.fromkeys(names))
    if len(names) < 2:
        raise E.EditError("Two files or more")
    if master not in names:
        raise E.EditError("The file they go into is one of them")
    groups = {f["name"]: f["group"] for f in E.files(cid)["files"]}
    order = list(groups)
    for n in names:
        E._file(cid, n)
        if groups.get(n) != category:
            raise E.EditError(("Only HTML files: " if category == "text" else "Only CSS files: ") + n.split("/")[-1])
    names.sort(key=order.index)
    return _changing(cid, "Merge into " + master.split("/")[-1],
                     lambda: _run(cid, {"op": "merge", "category": category, "names": names, "master": master}))


# ---------- Beautify ----------
def beautify(cid, name=None):
    """Calibre's Beautify, for one file or (name None) every HTML, CSS and XML file."""
    E._need(cid)
    if name:
        if not E._file(cid, name).is_file():
            raise E.EditError("No such file")
    return _changing(cid, "Beautify " + (name.split("/")[-1] if name else "all files"),
                     lambda: _run(cid, {"op": "pretty", "name": name or None}))


# ---------- Insert special character ----------
# The character map's categories, Calibre's own (calibre/gui2/tweak_book/char_select.py CategoryModel):
# (group, [(name, first, last)]).
CATEGORIES = [
    ('European scripts', [
        ('Armenian', 0x530, 0x58F), ('Armenian ligatures', 0xFB13, 0xFB17), ('Coptic', 0x2C80, 0x2CFF), ('Coptic in Greek block', 0x3E2, 0x3EF),
        ('Cypriot syllabary', 0x10800, 0x1083F), ('Cyrillic', 0x400, 0x4FF), ('Cyrillic supplement', 0x500, 0x52F),
        ('Cyrillic extended A', 0x2DE0, 0x2DFF), ('Cyrillic extended B', 0xA640, 0xA69F), ('Georgian', 0x10A0, 0x10FF),
        ('Georgian supplement', 0x2D00, 0x2D2F), ('Glagolitic', 0x2C00, 0x2C5F), ('Gothic', 0x10330, 0x1034F), ('Greek and Coptic', 0x370, 0x3FF),
        ('Greek extended', 0x1F00, 0x1FFF), ('Latin, Basic & Latin-1 supplement', 0x20, 0xFF), ('Latin extended A', 0x100, 0x17F),
        ('Latin extended B', 0x180, 0x24F), ('Latin extended C', 0x2C60, 0x2C7F), ('Latin extended D', 0xA720, 0xA7FF),
        ('Latin extended additional', 0x1E00, 0x1EFF), ('Latin ligatures', 0xFB00, 0xFB06), ('Fullwidth Latin letters', 0xFF00, 0xFF5E),
        ('Linear B syllabary', 0x10000, 0x1007F), ('Linear B ideograms', 0x10080, 0x100FF), ('Ogham', 0x1680, 0x169F),
        ('Old italic', 0x10300, 0x1032F), ('Phaistos disc', 0x101D0, 0x101FF), ('Runic', 0x16A0, 0x16FF), ('Shavian', 0x10450, 0x1047F),
    ]),
    ('Phonetic symbols', [
        ('IPA extensions', 0x250, 0x2AF), ('Phonetic extensions', 0x1D00, 0x1D7F), ('Phonetic extensions supplement', 0x1D80, 0x1DBF),
        ('Modifier tone letters', 0xA700, 0xA71F), ('Spacing modifier letters', 0x2B0, 0x2FF), ('Superscripts and subscripts', 0x2070, 0x209F),
    ]),
    ('Combining diacritics', [
        ('Combining diacritical marks', 0x300, 0x36F), ('Combining diacritical marks for symbols', 0x20D0, 0x20FF),
        ('Combining diacritical marks supplement', 0x1DC0, 0x1DFF), ('Combining half marks', 0xFE20, 0xFE2F),
    ]),
    ('African scripts', [
        ('Bamum', 0xA6A0, 0xA6FF), ('Bamum supplement', 0x16800, 0x16A3F), ('Egyptian hieroglyphs', 0x13000, 0x1342F), ('Ethiopic', 0x1200, 0x137F),
        ('Ethiopic supplement', 0x1380, 0x139F), ('Ethiopic extended', 0x2D80, 0x2DDF), ('Ethiopic extended A', 0xAB00, 0xAB2F),
        ('Meroitic cursive', 0x109A0, 0x109FF), ('Meroitic hieroglyphs', 0x10980, 0x1099F), ('Osmanya', 0x10480, 0x104AF),
        ('Tifinagh', 0x2D30, 0x2D7F), ('Vai', 0xA500, 0xA63F),
    ]),
    ('Middle Eastern scripts', [
        ('Arabic', 0x600, 0x6FF), ('Arabic supplement', 0x750, 0x77F), ('Arabic extended A', 0x8A0, 0x8FF),
        ('Arabic presentation forms A', 0xFB50, 0xFDFF), ('Arabic presentation forms B', 0xFE70, 0xFEFF), ('Avestan', 0x10B00, 0x10B3F),
        ('Carian', 0x102A0, 0x102DF), ('Cuneiform', 0x12000, 0x123FF), ('Cuneiform numbers and punctuation', 0x12400, 0x1247F),
        ('Hebrew', 0x590, 0x5FF), ('Hebrew presentation forms', 0xFB1D, 0xFB4F), ('Imperial Aramaic', 0x10840, 0x1085F),
        ('Inscriptional Pahlavi', 0x10B60, 0x10B7F), ('Inscriptional Parthian', 0x10B40, 0x10B5F), ('Lycian', 0x10280, 0x1029F),
        ('Lydian', 0x10920, 0x1093F), ('Mandaic', 0x840, 0x85F), ('Old Persian', 0x103A0, 0x103DF), ('Old South Arabian', 0x10A60, 0x10A7F),
        ('Phoenician', 0x10900, 0x1091F), ('Samaritan', 0x800, 0x83F), ('Syriac', 0x700, 0x74F), ('Ugaritic', 0x10380, 0x1039F),
    ]),
    ('Central Asian scripts', [
        ('Mongolian', 0x1800, 0x18AF), ('Old Turkic', 0x10C00, 0x10C4F), ('Phags-pa', 0xA840, 0xA87F), ('Tibetan', 0xF00, 0xFFF),
    ]),
    ('South Asian scripts', [
        ('Bengali', 0x980, 0x9FF), ('Brahmi', 0x11000, 0x1107F), ('Chakma', 0x11100, 0x1114F), ('Devanagari', 0x900, 0x97F),
        ('Devanagari extended', 0xA8E0, 0xA8FF), ('Gujarati', 0xA80, 0xAFF), ('Gurmukhi', 0xA00, 0xA7F), ('Kaithi', 0x11080, 0x110CF),
        ('Kannada', 0xC80, 0xCFF), ('Kharoshthi', 0x10A00, 0x10A5F), ('Lepcha', 0x1C00, 0x1C4F), ('Limbu', 0x1900, 0x194F),
        ('Malayalam', 0xD00, 0xD7F), ('Meetei Mayek', 0xABC0, 0xABFF), ('Meetei Mayek extensions', 0xAAE0, 0xAAEF), ('Ol Chiki', 0x1C50, 0x1C7F),
        ('Oriya', 0xB00, 0xB7F), ('Saurashtra', 0xA880, 0xA8DF), ('Sinhala', 0xD80, 0xDFF), ('Sharada', 0x11180, 0x111DF),
        ('Sora Sompeng', 0x110D0, 0x110FF), ('Syloti Nagri', 0xA800, 0xA82F), ('Takri', 0x11680, 0x116CF), ('Tamil', 0xB80, 0xBFF),
        ('Telugu', 0xC00, 0xC7F), ('Thaana', 0x780, 0x7BF), ('Vedic extensions', 0x1CD0, 0x1CFF),
    ]),
    ('Southeast Asian scripts', [
        ('Balinese', 0x1B00, 0x1B7F), ('Batak', 0x1BC0, 0x1BFF), ('Buginese', 0x1A00, 0x1A1F), ('Cham', 0xAA00, 0xAA5F), ('Javanese', 0xA980, 0xA9DF),
        ('Kayah Li', 0xA900, 0xA92F), ('Khmer', 0x1780, 0x17FF), ('Khmer symbols', 0x19E0, 0x19FF), ('Lao', 0xE80, 0xEFF),
        ('Myanmar', 0x1000, 0x109F), ('Myanmar extended A', 0xAA60, 0xAA7F), ('New Tai Lue', 0x1980, 0x19DF), ('Rejang', 0xA930, 0xA95F),
        ('Sundanese', 0x1B80, 0x1BBF), ('Sundanese supplement', 0x1CC0, 0x1CCF), ('Tai Le', 0x1950, 0x197F), ('Tai Tham', 0x1A20, 0x1AAF),
        ('Tai Viet', 0xAA80, 0xAADF), ('Thai', 0xE00, 0xE7F),
    ]),
    ('Philippine scripts', [
        ('Buhid', 0x1740, 0x175F), ('Hanunoo', 0x1720, 0x173F), ('Tagalog', 0x1700, 0x171F), ('Tagbanwa', 0x1760, 0x177F),
    ]),
    ('East Asian scripts', [
        ('Bopomofo', 0x3100, 0x312F), ('Bopomofo extended', 0x31A0, 0x31BF), ('CJK Unified ideographs', 0x4E00, 0x9FFF),
        ('CJK Unified ideographs extension A', 0x3400, 0x4DBF), ('CJK Unified ideographs extension B', 0x20000, 0x2A6DF),
        ('CJK Unified ideographs extension C', 0x2A700, 0x2B73F), ('CJK Unified ideographs extension D', 0x2B740, 0x2B81F),
        ('CJK compatibility ideographs', 0xF900, 0xFAFF), ('CJK compatibility ideographs supplement', 0x2F800, 0x2FA1F),
        ('Kangxi radicals', 0x2F00, 0x2FDF), ('CJK radicals supplement', 0x2E80, 0x2EFF), ('CJK strokes', 0x31C0, 0x31EF),
        ('Ideographic description characters', 0x2FF0, 0x2FFF), ('Hiragana', 0x3040, 0x309F), ('Katakana', 0x30A0, 0x30FF),
        ('Katakana phonetic extensions', 0x31F0, 0x31FF), ('Kana supplement', 0x1B000, 0x1B0FF), ('Halfwidth Katakana', 0xFF65, 0xFF9F),
        ('Kanbun', 0x3190, 0x319F), ('Hangul syllables', 0xAC00, 0xD7AF), ('Hangul Jamo', 0x1100, 0x11FF), ('Hangul Jamo extended A', 0xA960, 0xA97F),
        ('Hangul Jamo extended B', 0xD7B0, 0xD7FF), ('Hangul compatibility Jamo', 0x3130, 0x318F), ('Halfwidth Jamo', 0xFFA0, 0xFFDC),
        ('Lisu', 0xA4D0, 0xA4FF), ('Miao', 0x16F00, 0x16F9F), ('Yi syllables', 0xA000, 0xA48F), ('Yi radicals', 0xA490, 0xA4CF),
    ]),
    ('American scripts', [
        ('Cherokee', 0x13A0, 0x13FF), ('Deseret', 0x10400, 0x1044F), ('Unified Canadian aboriginal syllabics', 0x1400, 0x167F),
        ('UCAS extended', 0x18B0, 0x18FF),
    ]),
    ('Other', [
        ('Alphabetic presentation forms', 0xFB00, 0xFB4F), ('Halfwidth and Fullwidth forms', 0xFF00, 0xFFEF),
    ]),
    ('Punctuation', [
        ('General punctuation', 0x2000, 0x206F), ('ASCII punctuation', 0x21, 0x7F), ('Cuneiform numbers and punctuation', 0x12400, 0x1247F),
        ('Latin-1 punctuation', 0xA1, 0xBF), ('Small form variants', 0xFE50, 0xFE6F), ('Supplemental punctuation', 0x2E00, 0x2E7F),
        ('CJK symbols and punctuation', 0x3000, 0x303F), ('CJK compatibility forms', 0xFE30, 0xFE4F), ('Fullwidth ASCII punctuation', 0xFF01, 0xFF60),
        ('Vertical forms', 0xFE10, 0xFE1F),
    ]),
    ('Alphanumeric symbols', [
        ('Arabic mathematical alphabetic symbols', 0x1EE00, 0x1EEFF), ('Letterlike symbols', 0x2100, 0x214F), ('Roman symbols', 0x10190, 0x101CF),
        ('Mathematical alphanumeric symbols', 0x1D400, 0x1D7FF), ('Enclosed alphanumerics', 0x2460, 0x24FF),
        ('Enclosed alphanumeric supplement', 0x1F100, 0x1F1FF), ('Enclosed CJK letters and months', 0x3200, 0x32FF),
        ('Enclosed ideographic supplement', 0x1F200, 0x1F2FF), ('CJK compatibility', 0x3300, 0x33FF),
    ]),
    ('Technical symbols', [
        ('Miscellaneous technical', 0x2300, 0x23FF), ('Control pictures', 0x2400, 0x243F), ('Optical character recognition', 0x2440, 0x245F),
    ]),
    ('Numbers and digits', [
        ('Aegean numbers', 0x10100, 0x1013F), ('Ancient Greek numbers', 0x10140, 0x1018F), ('Common Indic number forms', 0xA830, 0xA83F),
        ('Counting rod numerals', 0x1D360, 0x1D37F), ('Cuneiform numbers and punctuation', 0x12400, 0x1247F),
        ('Fullwidth ASCII digits', 0xFF10, 0xFF19), ('Number forms', 0x2150, 0x218F), ('Rumi numeral symbols', 0x10E60, 0x10E7F),
        ('Superscripts and subscripts', 0x2070, 0x209F),
    ]),
    ('Mathematical symbols', [
        ('Arrows', 0x2190, 0x21FF), ('Supplemental arrows A', 0x27F0, 0x27FF), ('Supplemental arrows B', 0x2900, 0x297F),
        ('Miscellaneous symbols and arrows', 0x2B00, 0x2BFF), ('Mathematical alphanumeric symbols', 0x1D400, 0x1D7FF),
        ('Letterlike symbols', 0x2100, 0x214F), ('Mathematical operators', 0x2200, 0x22FF), ('Miscellaneous mathematical symbols A', 0x27C0, 0x27EF),
        ('Miscellaneous mathematical symbols B', 0x2980, 0x29FF), ('Supplemental mathematical operators', 0x2A00, 0x2AFF),
        ('Ceilings and floors', 0x2308, 0x230B), ('Geometric shapes', 0x25A0, 0x25FF), ('Box drawing', 0x2500, 0x257F),
        ('Block elements', 0x2580, 0x259F),
    ]),
    ('Musical symbols', [
        ('Musical symbols', 0x1D100, 0x1D1FF), ('More musical symbols', 0x2669, 0x266F), ('Ancient Greek musical notation', 0x1D200, 0x1D24F),
        ('Byzantine musical symbols', 0x1D000, 0x1D0FF),
    ]),
    ('Game symbols', [
        ('Chess', 0x2654, 0x265F), ('Domino tiles', 0x1F030, 0x1F09F), ('Draughts', 0x26C0, 0x26C3), ('Japanese chess', 0x2616, 0x2617),
        ('Mahjong tiles', 0x1F000, 0x1F02F), ('Playing cards', 0x1F0A0, 0x1F0FF), ('Playing card suits', 0x2660, 0x2667),
    ]),
    ('Other symbols', [
        ('Alchemical symbols', 0x1F700, 0x1F77F), ('Ancient symbols', 0x10190, 0x101CF), ('Braille patterns', 0x2800, 0x28FF),
        ('Currency symbols', 0x20A0, 0x20CF), ('Combining diacritical marks for symbols', 0x20D0, 0x20FF), ('Dingbats', 0x2700, 0x27BF),
        ('Emoticons', 0x1F600, 0x1F64F), ('Miscellaneous symbols', 0x2600, 0x26FF), ('Miscellaneous symbols and arrows', 0x2B00, 0x2BFF),
        ('Miscellaneous symbols and pictographs', 0x1F300, 0x1F5FF), ('Yijing hexagram symbols', 0x4DC0, 0x4DFF),
        ('Yijing mono and digrams', 0x268A, 0x268F), ('Yijing trigrams', 0x2630, 0x2637), ('Tai Xuan Jing symbols', 0x1D300, 0x1D35F),
        ('Transport and map symbols', 0x1F680, 0x1F6FF),
    ]),
    ('Other', [
        ('Specials', 0xFFF0, 0xFFFF), ('Tags', 0xE0000, 0xE007F), ('Variation selectors', 0xFE00, 0xFE0F),
        ('Variation selectors supplement', 0xE0100, 0xE01EF),
    ]),
]
# Calibre's default favourites (tprefs charmap_favorites, calibre/gui2/tweak_book/__init__.py).
FAVORITES = [ord(c) for c in ("\xa0   \xad" "‘’“”‹›«»‚„" "—–§¶†‡©®™" "→⇒•·°±−×÷¼½½¾" "…µ¢£€¿¡¨´¸ˆ˜"
                              "ÀÁÂÃÄÅÆÇÈÉÊË" "ÌÍÎÏÐÑÒÓÔÕÖØ" "ŒŠÙÚÛÜÝŸÞßàá" "âãäåæçèéêëìí" "îïðñòóôõöøœš" "ùúûüýÿþªºαΩ∞")]
MAX_CHARS = 2000
_names = []
_names_lock = threading.Lock()


def _name(cp):
    return unicodedata.name(chr(cp), "") or ("U+%04X" % cp)


def _index():
    """(code point, name) for every named character in the map's categories, built once."""
    with _names_lock:
        if not _names:
            seen = set()
            for _g, items in CATEGORIES:
                for _n, a, b in items:
                    for cp in range(a, b + 1):
                        if cp not in seen and not 0xD800 <= cp <= 0xDFFF:
                            seen.add(cp)
                            n = unicodedata.name(chr(cp), "")
                            if n:
                                _names.append((cp, n))
            _names.sort()
        return _names


def chars(q=None, first=None, last=None):
    """The character map: with no arguments, its categories and favourites; with q, the characters
    whose names have every word (a word starts with each one; U+2014 finds that one); with first and
    last, a category's characters. Each character as [code point, name], at most MAX_CHARS."""
    if q is not None:
        q = str(q).strip().lower()[:100]
        toks = q.split()
        if not toks:
            return {"chars": []}
        out = []
        for t in toks:
            m = re.fullmatch(r"(?:u\+|0x)([0-9a-f]{1,6})", t)
            if m and int(m.group(1), 16) <= 0x10FFFF:
                out.append([int(m.group(1), 16), _name(int(m.group(1), 16))])
        words = [t for t in toks if not re.fullmatch(r"(?:u\+|0x)[0-9a-f]{1,6}", t)]
        if words:
            for cp, n in _index():
                ws = n.lower().replace("-", " ").split()
                if all(any(w.startswith(t) for w in ws) for t in words):
                    out.append([cp, n])
                    if len(out) >= MAX_CHARS:
                        break
        return {"chars": out[:MAX_CHARS]}
    if first is not None and last is not None:
        a, b = max(0, int(first)), min(0x10FFFF, int(last))
        if b < a:
            return {"chars": []}
        out = [[cp, _name(cp)] for cp in range(a, min(b, a + MAX_CHARS - 1) + 1) if not 0xD800 <= cp <= 0xDFFF]
        return {"chars": [x for x in out if not x[1].startswith("U+") or unicodedata.category(chr(x[0])) not in ("Cn",)]}
    return {"categories": [[g, [[n, a, b] for n, a, b in items]] for g, items in CATEGORIES],
            "favorites": [[cp, _name(cp)] for cp in dict.fromkeys(FAVORITES)]}


# ---------- Check external links ----------
UA = "Mozilla/5.0 (Daf; checking links in a book)"
TIMEOUT, WORKERS, MAX_LINKS, MAX_HOPS = 8, 4, 400, 5


class NotWeb(Exception):
    pass


def public(url):
    """Daf's rule for the web: http(s) to a name whose every address is a public one (never Daf's own
    network: private, loopback, link-local, Tailscale's 100.64/10, reserved or multicast)."""
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise NotWeb("Not a web address")
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError):
        raise NotWeb("No such address")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
                or ip in ipaddress.ip_network("100.64.0.0/10")):
            raise NotWeb("Not an address on the web")


class _Hops(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to the web, and keeps where it went."""
    def __init__(self):
        self.hops = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if len(self.hops) >= MAX_HOPS:
            raise NotWeb("Too many redirects")
        public(newurl)
        self.hops.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ids(html):
    return set(re.findall(r"""\bid\s*=\s*["']([^"']+)""", html)) | set(re.findall(r"""<a\b[^>]*\bname\s*=\s*["']([^"']+)""", html, re.I))


def _dead(reason):
    """A failure GET won't get past either: no answer, refused, no such name, a bad certificate."""
    import ssl
    return isinstance(reason, (TimeoutError, socket.timeout, ConnectionRefusedError, socket.gaierror, ssl.SSLError))


def check_url(href):
    """One link: {status: ok | redirected | broken | skipped, code, error, url (where it ended up)}.
    HEAD first, GET when HEAD isn't answered or there's an #anchor to look for on the page (as
    Calibre's check does)."""
    url, _hash, frag = href.partition("#")
    try:
        public(url)
    except NotWeb as e:
        return {"status": "skipped", "error": str(e)}
    for method in (("GET",) if frag else ("HEAD", "GET")):
        hops = _Hops()
        last = lambda: hops.hops[-1] if hops.hops else None      # noqa: E731
        opener = urllib.request.build_opener(hops)
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                code, ctype = r.status, (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                body = r.read(2 * 1024 * 1024) if method == "GET" and frag and ctype in ("text/html", "application/xhtml+xml") else b""
        except urllib.error.HTTPError as e:
            if method == "HEAD":
                continue                        # some servers only answer GET
            return {"status": "broken", "code": e.code, "error": f"{e.code} {e.reason}", "url": last()}
        except NotWeb as e:
            return {"status": "broken", "error": str(e), "url": last()}
        except urllib.error.URLError as e:
            if method == "HEAD" and not _dead(e.reason):
                continue
            return {"status": "broken", "error": "No answer" if isinstance(e.reason, (TimeoutError, socket.timeout)) else str(e.reason)[:200], "url": last()}
        except (TimeoutError, socket.timeout):
            return {"status": "broken", "error": "No answer", "url": last()}
        except Exception as e:  # noqa: BLE001 - a dropped connection, a bad answer…
            if method == "HEAD":
                continue
            return {"status": "broken", "error": str(e)[:200] or e.__class__.__name__, "url": last()}
        if body and frag not in _ids(body.decode("utf-8", "replace")):
            return {"status": "broken", "code": code, "error": f"HTML anchor {frag} not found on the page", "url": last()}
        return {"status": "redirected" if hops.hops else "ok", "code": code, "url": last()}
    return {"status": "broken", "error": "No answer"}


def external_links(cid):
    """Check external links: every http(s) link Calibre finds in the book's HTML and CSS, fetched a
    few at a time. {links: [{href, at: [[name, line, col]], status, code, error, url}], more}."""
    E._need(cid)
    found = _run(cid, {"op": "links"}, timeout=300)["links"]
    todo, more = found[:MAX_LINKS], max(0, len(found) - MAX_LINKS)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda x: check_url(x["href"]), todo))
    order = {"broken": 0, "redirected": 1, "skipped": 2, "ok": 3}
    links = [dict(x, **r) for x, r in zip(todo, results)]
    links.sort(key=lambda x: (order.get(x["status"], 9), x["href"]))
    return {"links": links, "more": more}
