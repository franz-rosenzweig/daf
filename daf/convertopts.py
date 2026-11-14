"""Calibre's conversion settings, for the Convert sheet (web/convertsheet.js).

Which of Calibre's Convert dialog options Daf takes, each checked against its kind and range (an
option Daf doesn't know is dropped); ebook-convert's command-line flags for them, as a list; Daf's
own defaults (settings convert_opts, shared by every device); and a book's own settings, read from
Calibre's conversion_options table the way Calibre keeps them. Saving a book's settings is Calibre's
own save_specifics, run inside the container (calibrewrite's convert op).

The names, defaults and choices are Calibre 9.1's (the Plumber's options and each output plugin's),
as the Convert dialog saves them, so a book's settings mean the same thing here and in Calibre on
the Mac.
"""
import ast
import json
import logging
import math
import re
import struct
import subprocess

from . import config
from .db import read_only

log = logging.getLogger("daf.convertopts")

# Calibre's profiles: (short name, the name Calibre's Page setup shows)
OUTPUT_PROFILES = [
    ("default", "Default output profile"), ("cybookg3", "Cybook G3"), ("cybook_opus", "Cybook Opus"),
    ("generic_eink", "Generic e-ink"), ("generic_eink_hd", "Generic e-ink HD"), ("generic_eink_large", "Generic e-ink large"),
    ("hanlinv3", "Hanlin V3"), ("hanlinv5", "Hanlin V5"), ("illiad", "Illiad"), ("ipad", "iPad"), ("ipad3", "iPad 3"),
    ("irexdr1000", "IRex Digital Reader 1000"), ("irexdr800", "IRex Digital Reader 800"), ("jetbook5", "JetBook 5-inch"),
    ("kindle", "Kindle"), ("kindle_dx", "Kindle DX"), ("kindle_fire", "Kindle Fire"), ("kindle_oasis", "Kindle Oasis"),
    ("kindle_pw", "Kindle PaperWhite"), ("kindle_pw3", "Kindle PaperWhite 3"), ("kindle_scribe", "Kindle Scribe"),
    ("kindle_voyage", "Kindle Voyage"), ("kobo", "Kobo Reader"), ("msreader", "Microsoft Reader"), ("mobipocket", "Mobipocket Books"),
    ("nook", "Nook"), ("nook_color", "Nook Color"), ("nook_hd_plus", "Nook HD+"),
    ("pocketbook_inkpad3", "PocketBook Inkpad 3 (Pro) and X"), ("pocketbook_lux", "PocketBook Lux (1-5) and Basic 4"),
    ("pocketbook_hd", "PocketBook PocketBook HD Touch (1-3)"), ("pocketbook_900", "PocketBook Pro 900"),
    ("pocketbook_pro_912", "PocketBook Pro 912"), ("galaxy", "Samsung Galaxy"), ("sony", "Sony Reader"),
    ("sony300", "Sony Reader 300"), ("sony900", "Sony Reader 900"), ("sony-landscape", "Sony Reader Landscape"),
    ("sonyt3", "Sony Reader T3"), ("tablet", "Tablet"),
]
INPUT_PROFILES = [
    ("default", "Default input profile"), ("cybookg3", "Cybook G3"), ("cybook_opus", "Cybook Opus"), ("hanlinv3", "Hanlin V3"),
    ("hanlinv5", "Hanlin V5"), ("illiad", "Illiad"), ("irexdr1000", "IRex Digital Reader 1000"), ("irexdr800", "IRex Digital Reader 800"),
    ("kindle", "Kindle"), ("msreader", "Microsoft Reader"), ("mobipocket", "Mobipocket Books"), ("nook", "Nook"),
    ("sony", "Sony Reader"), ("sony300", "Sony Reader 300"), ("sony900", "Sony Reader 900"),
]
PAPER = ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "b0", "b1", "b2", "b3", "b4", "b5", "b6", "legal", "letter"]
CHOICES = {
    "output_profile": OUTPUT_PROFILES, "input_profile": INPUT_PROFILES,
    "change_justification": [("original", "Original"), ("left", "Left align"), ("justify", "Justify")],
    "chapter_mark": [("pagebreak", "Page break"), ("rule", "Rule"), ("both", "Both"), ("none", "None")],
    "epub_version": [("2", "2"), ("3", "3")],
    "mobi_file_type": [("old", "Old"), ("both", "Both"), ("new", "New")],
    "paper_size": [(p, p.title() if len(p) > 2 else p.upper()) for p in PAPER],
    "pdf_standard_font": [("serif", "Serif"), ("sans", "Sans"), ("mono", "Mono")],
}
CHAPTER = ("//*[((name()='h1' or name()='h2') and re:test(., '\\s*((chapter|book|section|part)\\s+)|"
           "((prolog|prologue|epilogue)(\\s+|$))', 'i')) or @class = 'chapter']")


def B(d):
    return {"t": "bool", "d": d}


def I(d, lo, hi):   # noqa: E743 - the kinds read as a table
    return {"t": "int", "d": d, "lo": lo, "hi": hi}


def F(d, lo, hi, cli=None):
    """A number with decimals. cli="int": ebook-convert's command line takes a whole number for it
    (its default there is 0, not 0.0), though Calibre's dialog keeps it with decimals."""
    return {"t": "float", "d": d, "lo": lo, "hi": hi, "cli": cli}


def E(d, key):
    return {"t": "enum", "d": d, "choices": [c[0] for c in CHOICES[key]]}


def S(d=None, n=300):
    return {"t": "text", "d": d, "n": n}


XPATH = 1000
# The pipeline's options (Look & feel, Page setup, Structure detection, Table of contents, Heuristic
# processing), the same for every output format. Calibre's own defaults.
PIPE = {
    # Look & feel
    "base_font_size": F(0.0, 0, 100, "int"), "font_size_mapping": {"t": "fontmap", "d": None},
    "minimum_line_height": F(120.0, 0, 900), "line_height": F(0.0, 0, 250, "int"),
    "embed_font_family": S(None, 100), "embed_all_fonts": B(False), "subset_embedded_fonts": B(False),
    "change_justification": E("original", "change_justification"),
    "smarten_punctuation": B(False), "unsmarten_punctuation": B(False),
    "remove_paragraph_spacing": B(False), "remove_paragraph_spacing_indent_size": F(1.5, -1, 20),
    "insert_blank_line": B(False), "insert_blank_line_size": F(0.5, 0, 20),
    "linearize_tables": B(False), "disable_font_rescaling": B(False),
    "extra_css": {"t": "css", "d": None, "n": 20000}, "filter_css": {"t": "props", "d": None},
    # Page setup
    "output_profile": E("default", "output_profile"), "input_profile": E("default", "input_profile"),
    "margin_top": F(5.0, -1, 500), "margin_bottom": F(5.0, -1, 500), "margin_left": F(5.0, -1, 500), "margin_right": F(5.0, -1, 500),
    # Structure detection
    "chapter": S(CHAPTER, XPATH), "chapter_mark": E("pagebreak", "chapter_mark"),
    "remove_first_image": B(False), "remove_fake_margins": B(True), "insert_metadata": B(False),
    # Table of contents
    "use_auto_toc": B(False), "no_chapters_in_toc": B(False), "max_toc_links": I(50, 0, 10000), "toc_threshold": I(6, 0, 10000),
    "level1_toc": S(None, XPATH), "level2_toc": S(None, XPATH), "level3_toc": S(None, XPATH),
    # Heuristic processing
    "enable_heuristics": B(False), "markup_chapter_headings": B(True), "italicize_common_cases": B(True),
    "fix_indents": B(True), "unwrap_lines": B(True), "html_unwrap_factor": F(0.4, 0, 1),
    "delete_blank_paragraphs": B(True), "format_scene_breaks": B(True), "replace_scene_breaks": S("", 200),
    "dehyphenate": B(True), "renumber_headings": B(True),
}
# Each output format's own options (Calibre's EPUB output, AZW3 output…).
OUT = {
    "EPUB": {
        "epub_version": E("2", "epub_version"), "flow_size": I(260, 0, 100000), "dont_split_on_page_breaks": B(False),
        "no_default_epub_cover": B(False), "no_svg_cover": B(False), "preserve_cover_aspect_ratio": B(False),
        "epub_inline_toc": B(False), "epub_toc_at_end": B(False), "toc_title": S(None, 200), "epub_flatten": B(False),
    },
    "AZW3": {
        "no_inline_toc": B(False), "mobi_toc_at_start": B(False), "toc_title": S(None, 200), "prefer_author_sort": B(False),
    },
    "MOBI": {
        "mobi_file_type": E("old", "mobi_file_type"), "no_inline_toc": B(False), "mobi_toc_at_start": B(False), "toc_title": S(None, 200),
        "prefer_author_sort": B(False), "mobi_keep_original_images": B(False), "mobi_ignore_margins": B(False),
    },
    "KEPUB": {
        "flow_size": I(512, 0, 100000), "dont_split_on_page_breaks": B(False), "kepub_prefer_justification": B(False),
        "kepub_disable_hyphenation": B(False), "kepub_affect_hyphenation": B(False), "kepub_hyphenation_min_chars": I(6, 0, 100),
        "kepub_hyphenation_min_chars_before": I(3, 0, 20), "kepub_hyphenation_min_chars_after": I(3, 0, 20),
        "kepub_hyphenation_limit_lines": I(2, 0, 20),
    },
    "PDF": {
        "paper_size": E("letter", "paper_size"), "use_profile_size": B(False), "pdf_default_font_size": I(20, 1, 100),
        "pdf_mono_font_size": I(16, 1, 100), "pdf_standard_font": E("serif", "pdf_standard_font"), "pdf_page_numbers": B(False),
        "pdf_add_toc": B(False), "toc_title": S(None, 200), "pdf_hyphenate": B(False), "preserve_cover_aspect_ratio": B(False),
        "pdf_no_cover": B(False), "pdf_use_document_margins": B(False),
        "pdf_page_margin_top": F(72.0, 0, 1000), "pdf_page_margin_bottom": F(72.0, 0, 1000),
        "pdf_page_margin_left": F(72.0, 0, 1000), "pdf_page_margin_right": F(72.0, 0, 1000),
    },
}
FILE_OPTS = {"extra_css"}      # given to ebook-convert as a file (calibrewrite writes it), never as text it might take for a path


def specs(to=None):
    """The options for one output format; for Daf's defaults (to=None), every format's."""
    if to is None:
        out = dict(PIPE)
        for o in OUT.values():
            for k, s in o.items():
                out.setdefault(k, s)
        return out
    return {**PIPE, **OUT.get(str(to).upper(), {})}


def defaults(to):
    return {k: s["d"] for k, s in specs(to).items()}


def calibre_defaults():
    """Calibre's own values: the pipeline's, and each output format's."""
    return {"pipe": {k: s["d"] for k, s in PIPE.items()}, "out": {f: {k: s["d"] for k, s in o.items()} for f, o in OUT.items()}}


_BAD = object()
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_PROP = re.compile(r"-?[a-z][a-z0-9-]{0,40}")
_FONTMAP = re.compile(r"\d{1,3}(\.\d{1,2})?(,\d{1,3}(\.\d{1,2})?){0,9}")


def _number(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _value(s, v):
    t = s["t"]
    if t == "bool":
        if isinstance(v, bool):
            return v
        if isinstance(v, int) and v in (0, 1):
            return bool(v)
        return _BAD
    if t in ("int", "float"):
        n = _number(v)
        if n is None:
            return _BAD
        n = float(min(s["hi"], max(s["lo"], n)))
        return int(round(n)) if t == "int" else round(n, 3)
    if t == "enum":
        v = str(v) if isinstance(v, (str, int)) and not isinstance(v, bool) else None
        return v if v in s["choices"] else _BAD
    if v is None:
        return None
    if not isinstance(v, str):
        return _BAD
    if t == "css":
        v = v.replace("\x00", "")[:s["n"]]
        return v if v.strip() else None
    if t == "props":           # Filter style information: CSS property names, a comma between
        names = [x.strip().lower() for x in v.split(",") if x.strip()]
        if any(not _PROP.fullmatch(x) for x in names):
            return _BAD
        return ",".join(dict.fromkeys(names))[:2000]
    if t == "fontmap":         # Font size key: 12,12,14,16,18,20,22,24
        v = re.sub(r"\s+", "", v)
        if not v:
            return None
        return v if _FONTMAP.fullmatch(v) else _BAD
    v = _CTRL.sub(" ", v).strip()[:s["n"]]
    return v if v or s["d"] == "" else None


def clean(opts, to=None):
    """The options Daf takes for this output format (every format's for to=None), each checked:
    numbers clamped to their range, choices from Calibre's list, text one line and capped. Anything
    else is dropped."""
    out = {}
    if not isinstance(opts, dict):
        return out
    sp = specs(to)
    for k, v in opts.items():
        s = sp.get(k)
        if s is None:
            continue
        v = _value(s, v)
        if v is not _BAD:
            out[k] = v
    return out


def _flag(k):
    return "--" + k.replace("_", "-")


def flags(opts, to):
    """ebook-convert's flags for these (clean) options, in a fixed order, each one argument: a switch
    when it differs from Calibre's default (--disable-… for the ones that are on by default), else
    --name=value. Empty values are left to Calibre. extra_css isn't here: it goes as a file."""
    out = []
    for k, s in specs(to).items():
        if k not in opts or k in FILE_OPTS:
            continue
        v = opts[k]
        if v is None or v == "":
            continue
        if s["t"] == "bool":
            if v != s["d"]:
                out.append(("--disable-" + k.replace("_", "-")) if s["d"] else _flag(k))
            continue
        if s.get("cli") == "int":
            v = int(round(v))
        out.append(f"{_flag(k)}={v}")
    return out


def to_save(opts, to):
    """What the book keeps in Calibre for this conversion: every option the sheet shows for this
    format, Calibre's default where the sheet left it alone, as Calibre's Convert dialog saves them."""
    return {**defaults(to), **clean(opts, to)}


# ---------- a book's own settings, as Calibre keeps them ----------
def _unpickle(data):
    """Calibre's unpickle_binary_string: the column holds a protocol-2 pickle of one byte string,
    read here by hand (no pickle.loads)."""
    data = bytes(data or b"")
    if data[:2] != b"\x80\x02":
        return None
    which, off = data[2:3], 3
    if which == b"T":
        (n,) = struct.unpack_from("<i", data, off)
        off += 4
    elif which == b"U":
        n = data[off]
        off += 1
    else:
        return None
    return data[off:off + n]


def parse(data):
    """A conversion_options row's data → Calibre's settings dict ({} when it can't be read). Calibre
    9 writes "json:" and the JSON; older Calibre wrote a Python literal."""
    raw = _unpickle(data)
    if raw is None:
        return {}
    try:
        if raw.startswith(b"json:"):
            d = json.loads(raw[5:].decode("utf-8"))
        else:
            d = ast.literal_eval(raw.decode("utf-8"))
    except (ValueError, SyntaxError, UnicodeDecodeError, MemoryError, RecursionError):
        return {}
    return d if isinstance(d, dict) else {}


def book_opts(cid):
    """A book's own settings from Calibre (read-only), the options Daf takes, and the input format
    Calibre's dialog last used for it (upper case, or None)."""
    c = read_only(config.CALIBRE_DBS[0])
    try:
        row = c.execute("SELECT data FROM conversion_options WHERE book = ? AND format = 'PIPE' COLLATE NOCASE", (int(cid),)).fetchone()
    except Exception:  # noqa: BLE001 - a library without the table
        row = None
    finally:
        c.close()
    d = parse(row[0]) if row else {}
    src = d.get("gui_preferred_input_format")
    return clean(d), (str(src).upper()[:10] if isinstance(src, str) and src else None)


# ---------- the fonts Calibre can embed (the container's) ----------
FONTS = r'''
import json
from calibre.utils.fonts.scanner import font_scanner
print("DAFRESULT " + json.dumps(list(font_scanner.find_font_families())))
'''
_fonts = []


def fonts():
    if _fonts:
        return list(_fonts)
    from . import calibrewrite
    try:
        r = subprocess.run(calibrewrite.RUN + [calibrewrite.DEBUG, "-c", FONTS], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
        found = json.loads(line[len("DAFRESULT "):]) if line else []
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        log.warning("fonts: %s", e)
        found = []
    _fonts[:] = [str(f) for f in found if isinstance(f, str)][:500]
    return list(_fonts)
