"""Edit book: the inside of a Calibre book (its HTML, CSS, OPF, NCX, images and fonts), the way
Calibre's own Edit book does it, from Daf.

Everything happens on a working copy, and Calibre's book changes only on Save. The copy lives in
EDIT_DIR/<calibre id>/ (default /srv/docker/cwa/.daf-edit, which is /config/.daf-edit inside
Calibre-Web Automated's container), so Daf on the host and calibre-debug in the container (user
abc, uid 1000 like the host's) both read and write it:

    meta.json            the book, its format, when it was opened, whether it has changes Calibre doesn't have yet
    book/                the book as an EPUB folder (an AZW3 is opened into one, a KEPUB without its Kobo spans)
    checkpoints/<n>/     the folder as it was before a tool changed it (the last KEEP_CHECKPOINTS)
    out.<fmt>            the rebuilt book, while saving

Daf itself lists the files, reads and writes their text, serves them for the preview and does find
and replace (plain Python on the host). Calibre (calibre-debug, through calibrewrite's RUN and DEBUG)
opens the book into the folder, runs its checker, reads and writes the Table of Contents, runs
Polish's tools, adds, renames and removes files, and builds the book again for Save, which goes
into Calibre with calibrewrite's add_format op, so Calibre records it and Daf's rows follow.

    DAF_EDIT_DIR       the working copies on the host (default /srv/docker/cwa/.daf-edit)
    DAF_EDIT_DIR_IN    the same folder as calibre-debug sees it (default /config/.daf-edit)
"""
import html
import json
import logging
import mimetypes
import posixpath
import re
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from . import config

log = logging.getLogger("daf.ebookedit")
EDIT_DIR = Path(config.setting("DAF_EDIT_DIR", "/srv/docker/cwa/.daf-edit"))
EDIT_DIR_IN = config.setting("DAF_EDIT_DIR_IN", "/config/.daf-edit")
FORMATS = ("EPUB", "AZW3", "KEPUB")        # what Edit book opens, in the order it prefers them
KEEP_CHECKPOINTS = 10
MAX_TEXT = 12 * 1024 * 1024                 # a text file bigger than this isn't opened in the editor
MAX_MATCHES = 5000                          # matches listed back (the count is always all of them)
GROUPS = ("text", "styles", "images", "fonts", "other")
TOOLS = {"subset": "Subset fonts", "compress_images": "Compress images", "remove_unused_css": "Remove unused CSS",
         "smarten_punctuation": "Smarten punctuation", "upgrade_book": "Upgrade book internals"}
_EXT_TYPES = {"xhtml": "application/xhtml+xml", "html": "application/xhtml+xml", "htm": "application/xhtml+xml",
              "css": "text/css", "opf": "application/oebps-package+xml", "ncx": "application/x-dtbncx+xml",
              "xml": "application/xml", "svg": "image/svg+xml", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "png": "image/png", "gif": "image/gif", "webp": "image/webp", "ttf": "font/ttf", "otf": "font/otf",
              "woff": "font/woff", "woff2": "font/woff2", "txt": "text/plain", "js": "text/javascript",
              "smil": "application/smil+xml", "xpgt": "application/adobe-page-template+xml"}
_SYNTAX = {"application/xhtml+xml": "html", "text/html": "html", "text/css": "css", "application/oebps-package+xml": "xml",
           "application/x-dtbncx+xml": "xml", "application/xml": "xml", "text/xml": "xml", "image/svg+xml": "xml",
           "application/smil+xml": "xml", "application/adobe-page-template+xml": "xml", "text/plain": "text"}
_PROTECTED = {"mimetype", "META-INF/container.xml"}


class EditError(RuntimeError):
    pass


# ---------- where things are ----------
def home(cid):
    return EDIT_DIR / str(int(cid))


def book_dir(cid):
    return home(cid) / "book"


def inside(path):
    """A path under EDIT_DIR as calibre-debug sees it."""
    return EDIT_DIR_IN.rstrip("/") + "/" + Path(path).relative_to(EDIT_DIR).as_posix()


def _file(cid, name):
    """The host path of a file in the working copy, refusing anything outside it."""
    name = str(name or "")
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise EditError("No such file")
    root = book_dir(cid).resolve()
    p = (root / name).resolve()
    if root not in p.parents:
        raise EditError("No such file")
    return p


_locks, _locks_lock = {}, threading.Lock()


def _lock(cid):
    """One writer at a time per book: a text save waits while a Calibre tool has the folder."""
    with _locks_lock:
        return _locks.setdefault(int(cid), threading.RLock())


# ---------- meta ----------
def meta(cid):
    try:
        return json.loads((home(cid) / "meta.json").read_text())
    except (OSError, ValueError):
        return None


def _put_meta(cid, m):
    p = home(cid) / "meta.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m))
    tmp.replace(p)


def _changed(cid):
    m = meta(cid)
    if m and not m.get("changed"):
        m["changed"] = True
        _put_meta(cid, m)


def _source(cid, fmt):
    from . import catalog
    return catalog.book_file(cid, fmt)


def _stamp(p):
    st = p.stat()
    return {"size": st.st_size, "mtime": st.st_mtime_ns}


def _calibre_book(cid):
    """(title, the formats Edit book can open) from Calibre's database, read only."""
    from . import catalog
    db = config.CALIBRE_DBS[0]
    c = catalog.read_only(db)
    try:
        r = c.execute("SELECT title FROM books WHERE id = ?", (int(cid),)).fetchone()
        have = {f.upper() for (f,) in c.execute("SELECT format FROM data WHERE book = ?", (int(cid),))}
    finally:
        c.close()
    if not r:
        return None, []
    return r[0], [f for f in FORMATS if f in have]


def status(cid):
    """{title, formats, copy: meta | None, stale: Calibre's file changed since the copy was made}."""
    title, fmts = _calibre_book(cid)
    if title is None:
        raise EditError("Calibre has no such book")
    m = meta(cid)
    stale = False
    if m:
        p = _source(cid, m["fmt"])
        stale = not p or _stamp(p) != m.get("src")
        if stale and not m.get("changed"):         # nothing of mine in it: the copy just goes
            discard(cid)
            m, stale = None, False
    return {"title": title, "formats": fmts, "copy": m, "stale": stale}


# ---------- Calibre, in the container ----------
# Runs in Calibre's own Python (calibre-debug -c). The job comes on stdin as JSON, the answer goes
# back on the last line of stdout after DAFRESULT. Everything is inside main(), because calibre-debug
# -c runs the script with separate globals and locals.
SCRIPT = r'''
def main():
    import json, os, shutil, sys, tempfile, traceback
    job = json.loads(sys.stdin.read())
    work = job["dir"]
    book = os.path.join(work, "book")
    tmp = tempfile.mkdtemp(prefix="tmp-", dir=work)
    out = {"ok": True}
    from calibre.utils.logging import Log
    quiet = Log(level=Log.ERROR)

    def container(path=None, **kw):
        from calibre.ebooks.oeb.polish.container import get_container
        return get_container(path or book, log=quiet, tweak_mode=True, tdir=tempfile.mkdtemp(dir=tmp), **kw)

    def errors(c):
        from calibre.ebooks.oeb.polish.check.main import run_checks
        from calibre.ebooks.oeb.polish.check.base import ERROR, WARN
        res = []
        for e in run_checks(c):
            res.append({"level": "error" if e.level >= ERROR else "warning" if e.level == WARN else "info",
                        "msg": str(e.msg), "name": e.name, "line": e.line, "col": e.col,
                        "help": str(getattr(e, "HELP", "") or ""), "fixable": bool(getattr(e, "fixable", False))})
        return res

    def tree(t):
        return [{"title": ch.title or "", "dest": ch.dest, "frag": ch.frag or None,
                 "missing": bool(ch.dest and not ch.dest_exists), "children": tree(ch)} for ch in t]

    def mimetype():
        p = os.path.join(book, "mimetype")
        with open(p, "wb") as f:
            f.write(b"application/epub+zip")

    try:
        op = job["op"]
        if op == "open":
            src, fmt = job["src"], job["fmt"].upper()
            if os.path.exists(book):
                shutil.rmtree(book)
            if fmt == "AZW3":
                # Calibre opens an AZW3 into an OPF and its files; with a container.xml it is an EPUB folder
                from xml.sax.saxutils import quoteattr
                c = container(src)
                shutil.copytree(c.root, book)
                os.makedirs(os.path.join(book, "META-INF"), exist_ok=True)
                with open(os.path.join(book, "META-INF", "container.xml"), "w", encoding="utf-8") as f:
                    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                            '  <rootfiles>\n    <rootfile full-path=%s media-type="application/oebps-package+xml"/>\n  </rootfiles>\n</container>\n' % quoteattr(c.opf_name))
                mimetype()
            else:
                os.makedirs(book)
                try:
                    from calibre.utils.zipfile import ZipFile
                    with open(src, "rb") as s:
                        ZipFile(s).extractall(book)
                except Exception:
                    from calibre.utils.localunzip import extractall
                    with open(src, "rb") as s:
                        extractall(s, path=book)
            c = container()                     # a book Calibre can't open (no OPF, DRM) stops here
            if fmt == "KEPUB":
                from calibre.ebooks.oeb.polish.kepubify import unkepubify_container
                unkepubify_container(c)
                c.commit()
            out["files"] = len(c.name_path_map)
        elif op == "check":
            out["errors"] = errors(container())
        elif op == "fix":
            from calibre.ebooks.oeb.polish.check.main import fix_errors, run_checks
            c = container()
            out["changed"] = bool(fix_errors(c, run_checks(c)))
            if out["changed"]:
                c.commit()
            out["errors"] = errors(c)
        elif op == "toc":
            from calibre.ebooks.oeb.polish.toc import get_toc
            t = get_toc(container())
            out["toc"], out["title"] = tree(t), t.toc_title or ""
        elif op == "toc_generate":
            from calibre.ebooks.oeb.polish.toc import from_xpaths, from_files, from_links
            c = container()
            kind = job.get("kind") or "major"
            if kind == "files":
                t = from_files(c)
            elif kind == "links":
                t = from_links(c)
            else:
                t = from_xpaths(c, ["//h:h%d" % i for i in range(1, 4 if kind == "major" else 7)], prefer_title=True)
            c.commit()                          # the ids it gave the headings, for the entries to point at
            out["toc"] = tree(t)
        elif op == "toc_save":
            from calibre.ebooks.oeb.polish.toc import TOC, commit_toc, get_toc
            c = container()
            old = get_toc(c)
            t = TOC()
            t.toc_title = job.get("title") or old.toc_title
            def build(parent, items):
                for it in items:
                    ch = parent.add(str(it.get("title") or ""), it.get("dest") or None, it.get("frag") or None)
                    build(ch, it.get("children") or [])
            build(t, job["toc"])
            commit_toc(c, t, lang=getattr(old, "lang", None), uid=getattr(old, "uid", None))
            c.commit()
            out["toc"] = tree(get_toc(c))
        elif op == "polish":
            from calibre.ebooks.oeb.polish.main import tweak_polish, CUSTOMIZATION
            c = container()
            report, changed = tweak_polish(c, {job["tool"]: True}, customization=dict(CUSTOMIZATION))
            if changed:
                c.commit()
            out["report"] = [str(x) for x in report if str(x).strip()]
            out["changed"] = bool(changed)
        elif op == "remove":
            from calibre.ebooks.oeb.polish.toc import remove_names_from_toc
            c = container()
            names = [n for n in job["names"] if n in c.name_path_map and n != c.opf_name]
            for n in names:
                c.remove_item(n)
            try:
                remove_names_from_toc(c, names)
            except Exception:
                pass
            c.commit()
            out["removed"] = names
        elif op == "rename":
            from calibre.ebooks.oeb.polish.replace import rename_files
            c = container()
            m = {a: b for a, b in job["map"].items() if a != b}
            for a, b in m.items():
                if a not in c.name_path_map:
                    raise ValueError("No such file: " + a)
                if b in c.name_path_map:
                    raise ValueError("There's a file called " + b + " already")
            rename_files(c, m)
            c.commit()
        elif op == "add":
            from calibre.ebooks.oeb.polish.replace import get_recommended_folders
            c = container()
            name = job["name"]
            if "/" not in name:                 # beside the files of its kind, as Calibre does
                folder = get_recommended_folders(c, [name]).get(name) or ""
                name = folder.rstrip("/") + "/" + name if folder else name
            with open(job["src"], "rb") as f:
                data = f.read()
            got = c.add_file(name, data, modify_name_if_needed=True)
            c.commit()
            out["name"] = got if isinstance(got, str) else name
        elif op == "build":
            from calibre.ebooks.tweak import zip_rebuilder
            fmt, dest = job["fmt"].upper(), job["out"]
            container()                         # Calibre can still open it
            mimetype()
            if fmt == "EPUB":
                zip_rebuilder(book, dest)
            else:
                epub = os.path.join(tmp, "book.epub")
                zip_rebuilder(book, epub)
                if fmt == "KEPUB":
                    from calibre.ebooks.oeb.polish.kepubify import kepubify_container, Options
                    k = container(epub)
                    kepubify_container(k, Options())
                    k.commit(dest)
                elif fmt == "AZW3":
                    from calibre.ebooks.oeb.polish.container import epub_to_azw3
                    epub_to_azw3(epub, dest)
                else:
                    raise ValueError("Edit book doesn't write " + fmt)
            out["size"] = os.path.getsize(dest)
        else:
            raise ValueError("unknown op " + op)
    except Exception as e:
        msg = str(e) or e.__class__.__name__
        if e.__class__.__name__ == "DRMError":
            msg = "The book is locked (DRM)"
        out = {"ok": False, "error": msg, "trace": traceback.format_exc()[-1500:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("DAFRESULT " + json.dumps(out))
main()
'''


def _run(cid, job, timeout=600):
    """One job for Calibre on this book's working copy; its answer, or EditError."""
    from . import calibrewrite as W
    for old in home(cid).glob("tmp-*"):          # left by a run that was cut off
        shutil.rmtree(old, ignore_errors=True)
    job = dict(job, dir=inside(home(cid)))
    try:
        r = subprocess.run(W.RUN + [W.DEBUG, "-c", SCRIPT], input=json.dumps(job), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise EditError("Calibre took too long")
    except OSError as e:
        raise EditError(f"Couldn't reach Calibre: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        log.warning("calibre-debug said: %s %s", r.stdout[-800:], r.stderr[-800:])
        raise EditError("Calibre didn't answer")
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        log.warning("edit book %s failed: %s", job.get("op"), out.get("trace"))
        raise EditError(out.get("error") or "Calibre said no")
    return out


# ---------- the working copy ----------
def open_copy(cid, fmt=None):
    """Makes the working copy from Calibre's file (the first of FORMATS the book has, or fmt)."""
    title, fmts = _calibre_book(cid)
    if title is None:
        raise EditError("Calibre has no such book")
    fmt = (fmt or (fmts[0] if fmts else "")).upper()
    if fmt not in FORMATS:
        raise EditError("Edit book opens " + ", ".join(FORMATS))
    src = _source(cid, fmt)
    if not src:
        raise EditError(f"The book has no {fmt} file")
    with _lock(cid):
        h = home(cid)
        if h.exists():
            shutil.rmtree(h)
        h.mkdir(parents=True)
        copy = h / ("source." + fmt.lower())
        shutil.copyfile(src, copy)
        try:
            _run(cid, {"op": "open", "src": inside(copy), "fmt": fmt})
        except Exception:
            shutil.rmtree(h, ignore_errors=True)
            raise
        copy.unlink(missing_ok=True)
        m = {"id": int(cid), "fmt": fmt, "title": title, "opened": int(time.time()), "src": _stamp(src), "changed": False, "saved": None}
        _put_meta(cid, m)
    return m


def discard(cid):
    with _lock(cid):
        shutil.rmtree(home(cid), ignore_errors=True)


def close(cid):
    """Leaving the editor: a copy without changes goes, one with changes stays for next time."""
    m = meta(cid)
    if m and not m.get("changed"):
        discard(cid)
        return {"kept": False}
    return {"kept": bool(m)}


def _need(cid):
    m = meta(cid)
    if not m or not book_dir(cid).is_dir():
        raise EditError("The book isn't open for editing")
    return m


def opf_name(cid):
    root = book_dir(cid)
    try:
        for el in ET.parse(root / "META-INF" / "container.xml").getroot().iter():
            if el.tag.rsplit("}", 1)[-1] == "rootfile" and el.get("full-path") and \
                    (el.get("media-type") or "application/oebps-package+xml") == "application/oebps-package+xml":
                return el.get("full-path")
    except (OSError, ET.ParseError):
        pass
    found = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.opf"))
    return found[0] if found else None


def _manifest(cid):
    """(opf name, {name: media type}, [spine names]) from the OPF, read by Daf itself."""
    opf = opf_name(cid)
    types, spine = {}, []
    if not opf:
        return None, types, spine
    try:
        root = ET.parse(_file(cid, opf)).getroot()
    except (OSError, ET.ParseError, EditError):
        return opf, types, spine
    base = posixpath.dirname(opf)
    ids = {}
    for it in root.iterfind(".//{*}manifest/{*}item"):
        href = it.get("href")
        if not href:
            continue
        name = posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0])))
        types[name] = (it.get("media-type") or "").strip().lower()
        ids[it.get("id")] = name
    for ref in root.iterfind(".//{*}spine/{*}itemref"):
        n = ids.get(ref.get("idref"))
        if n and n not in spine:
            spine.append(n)
    return opf, types, spine


def _type_of(name, types):
    t = types.get(name)
    if t:
        return t
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return _EXT_TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def group_of(name, mt):
    """Calibre's file browser's groups: Text, Styles, Images, Fonts and the rest."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if mt in ("application/xhtml+xml", "text/html") or ext in ("xhtml", "html", "htm"):
        return "text"
    if mt == "text/css" or ext == "css":
        return "styles"
    if mt.startswith("image/"):
        return "images"
    if mt.startswith("font/") or "font" in mt or ext in ("ttf", "otf", "woff", "woff2"):
        return "fonts"
    return "other"


def files(cid):
    """The book's files, grouped and in Calibre's order: text in the spine's order (then the rest),
    the OPF and NCX first under Other, everything else by name."""
    _need(cid)
    root = book_dir(cid)
    opf, types, spine = _manifest(cid)
    order = {n: i for i, n in enumerate(spine)}
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.relative_to(root).as_posix()
        if name == "mimetype":
            continue
        mt = _type_of(name, types)
        g = group_of(name, mt)
        syn = _SYNTAX.get(mt) or ("xml" if name.endswith((".xml", ".opf", ".ncx", ".svg")) else None)
        out.append({"name": name, "group": g, "type": mt, "size": p.stat().st_size, "syntax": syn,
                    "editable": bool(syn) and p.stat().st_size <= MAX_TEXT, "spine": order.get(name),
                    "listed": name in types})
    first = {opf: 0}
    for f in out:
        if f["type"] == "application/x-dtbncx+xml":
            first[f["name"]] = 1

    def key(f):
        g = GROUPS.index(f["group"])
        if f["group"] == "text":
            return (g, 0 if f["spine"] is not None else 1, f["spine"] if f["spine"] is not None else 0, f["name"].lower())
        return (g, first.get(f["name"], 2), 0, f["name"].lower())
    out.sort(key=key)
    return {"files": out, "opf": opf}


# ---------- text ----------
def decode(raw):
    """(text with \\n line ends, the encoding to write it back in)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        text, enc = raw[3:].decode("utf-8", "replace"), "utf-8-sig"
    elif raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text, enc = raw.decode("utf-16", "replace"), "utf-16"
    else:
        try:
            text, enc = raw.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            m = re.search(rb'''^\s*<\?xml[^>]*encoding\s*=\s*["']([A-Za-z0-9._-]+)''', raw[:300]) or \
                re.search(rb'''<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9._-]+)''', raw[:4096], re.I)
            enc = m.group(1).decode("ascii") if m else "cp1252"
            try:
                text = raw.decode(enc, "replace")
            except LookupError:
                text, enc = raw.decode("cp1252", "replace"), "cp1252"
    return text.replace("\r\n", "\n").replace("\r", "\n"), enc


def encode(text, enc):
    if enc == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    if enc.lower().replace("_", "-") in ("utf-8", "utf8", "utf-16"):
        return text.encode(enc)
    return text.encode(enc, "xmlcharrefreplace")


def read_text(cid, name):
    _need(cid)
    p = _file(cid, name)
    if not p.is_file():
        raise EditError("No such file")
    if p.stat().st_size > MAX_TEXT:
        raise EditError("Too big to edit here")
    return decode(p.read_bytes())[0]


def write_text(cid, name, text):
    """Saves one file's text into the working copy. Returns whether anything changed."""
    _need(cid)
    if not isinstance(text, str):
        raise EditError("text: a string")
    with _lock(cid):
        p = _file(cid, name)
        if not p.is_file():
            raise EditError("No such file")
        old, enc = decode(p.read_bytes())
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text == old:
            return False
        tmp = p.with_name(p.name + ".daf-tmp")
        tmp.write_bytes(encode(text, enc))
        tmp.replace(p)
        _changed(cid)
    return True


# ---------- find and replace ----------
def pattern(find, regex=False, case=False):
    """Calibre's search: the regex module with Edit book's flags when it's there (as in Daf's own
    virtualenv), else Python's re. Normal mode looks for the words as they are."""
    if not find:
        raise EditError("Nothing to find")
    try:
        import regex as rx
    except ImportError:
        rx = None
    try:
        if rx:
            flags = rx.VERSION1 | rx.WORD | rx.FULLCASE | rx.MULTILINE | rx.UNICODE | (0 if case else rx.IGNORECASE)
            return rx.compile(find if regex else rx.escape(find, special_only=True), flags)
        return re.compile(find if regex else re.escape(find), re.MULTILINE | (0 if case else re.IGNORECASE))
    except Exception as e:  # noqa: BLE001 - re.error, regex.error
        raise EditError(f"The expression doesn't work: {e}")


def _scope(cid, where, name):
    if where == "file":
        if not name:
            raise EditError("No file open")
        return [name]
    group = {"text": "text", "styles": "styles"}.get(where)
    if not group:
        raise EditError("Where: file, text or styles")
    return [f["name"] for f in files(cid)["files"] if f["group"] == group and f["editable"]]


class _U16:
    """Offsets in UTF-16 code units (what the browser's editor counts) for offsets in a Python string."""
    def __init__(self, text):
        self.text, self.at, self.u = text, 0, 0
        self.wide = re.search("[\U00010000-\U0010ffff]", text) is not None

    def __call__(self, i):
        if not self.wide:
            return i
        if i < self.at:
            self.at, self.u = 0, 0
        self.u += sum(2 if ord(ch) > 0xFFFF else 1 for ch in self.text[self.at:i])
        self.at = i
        return self.u


def find(cid, spec):
    """{find, regex, case, where (file | text | styles), name} → {total, files: {name: count}, matches:
    [{name, start, end, line}]} with start and end in UTF-16 units, as the editor counts."""
    _need(cid)
    pat = pattern(spec.get("find"), spec.get("regex"), spec.get("case"))
    total, per, matches = 0, {}, []
    for name in _scope(cid, spec.get("where") or "file", spec.get("name")):
        try:
            text = read_text(cid, name)
        except EditError:
            continue
        u16, n, line, last = _U16(text), 0, 1, 0
        for m in pat.finditer(text):
            n += 1
            if len(matches) < MAX_MATCHES:
                line += text.count("\n", last, m.start())
                last = m.start()
                matches.append({"name": name, "start": u16(m.start()), "end": u16(m.end()), "line": line})
        if n:
            per[name] = n
            total += n
    return {"total": total, "files": per, "matches": matches}


def _replacer(template, regex):
    if not regex:
        return lambda m: template
    return lambda m: m.expand(template)


def replace(cid, spec):
    """Replace: all matches in the scope, or with `at` (a UTF-16 offset in `name`) the one match that
    starts there. Several files at once get a checkpoint first. → {total, files, change?: {from, to,
    insert} (the one match's change, in UTF-16 units)}."""
    _need(cid)
    pat = pattern(spec.get("find"), spec.get("regex"), spec.get("case"))
    rep = _replacer(str(spec.get("replace") or ""), spec.get("regex"))
    at = spec.get("at")
    with _lock(cid):
        if at is not None:
            name = spec.get("name")
            text = read_text(cid, name)
            u16 = _U16(text)
            for m in pat.finditer(text):
                s = u16(m.start())
                if s > int(at):
                    break
                if s == int(at):
                    try:
                        new = rep(m)
                    except Exception as e:  # noqa: BLE001 - a group that isn't there
                        raise EditError(f"The replacement doesn't work: {e}")
                    write_text(cid, name, text[:m.start()] + new + text[m.end():])
                    return {"total": 1, "files": {name: 1}, "change": {"from": s, "to": u16(m.end()), "insert": new}}
            return {"total": 0, "files": {}}
        names = _scope(cid, spec.get("where") or "file", spec.get("name"))
        texts, per = {}, {}
        for name in names:
            try:
                text = read_text(cid, name)
            except EditError:
                continue
            try:
                new, n = pat.subn(rep, text)
            except Exception as e:  # noqa: BLE001 - a group that isn't there
                raise EditError(f"The replacement doesn't work: {e}")
            if n:
                texts[name], per[name] = new, n
        if len(texts) > 1 or (texts and spec.get("where") != "file"):
            checkpoint(cid, "Replace all")
        for name, new in texts.items():
            write_text(cid, name, new)
    return {"total": sum(per.values()), "files": per}


def ids(cid, name):
    """The places in an HTML file a Table of Contents entry can point at: [{id, tag, text}]."""
    text = read_text(cid, name)
    out, seen = [], set()
    for m in re.finditer(r'''<([A-Za-z][\w:.-]*)\b[^>]*?\sid\s*=\s*(["'])(.*?)\2[^>]*>''', text, re.S):
        i = m.group(3)
        if i in seen:
            continue
        seen.add(i)
        after = html.unescape(re.sub(r"<[^>]*$", "", re.sub(r"<[^>]+>", " ", text[m.end():m.end() + 400])))
        t = re.sub(r"\s+", " ", after).strip()
        out.append({"id": i, "tag": m.group(1).lower(), "text": t if len(t) <= 80 else t[:80].rsplit(" ", 1)[0] + "…"})
    return out


def raw(cid, name):
    """(host path, media type) of a file, for the preview and the images."""
    _need(cid)
    p = _file(cid, name)
    if not p.is_file():
        raise EditError("No such file")
    return p, _type_of(name, _manifest(cid)[1])


# ---------- checkpoints ----------
def _cps(cid):
    try:
        return json.loads((home(cid) / "checkpoints.json").read_text())
    except (OSError, ValueError):
        return []


def checkpoints(cid):
    return list(reversed(_cps(cid)))


def checkpoint(cid, label):
    """The folder as it is now, kept before a tool changes it."""
    with _lock(cid):
        lst = _cps(cid)
        n = max([c["n"] for c in lst], default=0) + 1
        dest = home(cid) / "checkpoints" / str(n)
        dest.parent.mkdir(exist_ok=True)
        shutil.copytree(book_dir(cid), dest)
        lst.append({"n": n, "label": label, "at": int(time.time())})
        while len(lst) > KEEP_CHECKPOINTS:
            old = lst.pop(0)
            shutil.rmtree(home(cid) / "checkpoints" / str(old["n"]), ignore_errors=True)
        (home(cid) / "checkpoints.json").write_text(json.dumps(lst))
        return n


def _drop_checkpoint(cid, n):
    lst = [c for c in _cps(cid) if c["n"] != n]
    shutil.rmtree(home(cid) / "checkpoints" / str(n), ignore_errors=True)
    (home(cid) / "checkpoints.json").write_text(json.dumps(lst))


def restore(cid, n):
    """Back to how the book was at a checkpoint (the checkpoint stays, to go back to again)."""
    _need(cid)
    with _lock(cid):
        src = home(cid) / "checkpoints" / str(int(n))
        if not src.is_dir():
            raise EditError("No such checkpoint")
        tmp = home(cid) / "book.restoring"
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(src, tmp)
        shutil.rmtree(book_dir(cid))
        tmp.rename(book_dir(cid))
        _changed(cid)
    return {"ok": True}


# ---------- Calibre's tools on the copy ----------
LABELS = {"fix": "Fix all", "toc_save": "Contents", "remove": "Remove", "rename": "Rename", "add": "Add a file"}


def tool(cid, op, args=None):
    """Runs one of Calibre's tools on the working copy (SCRIPT's ops). Those that change the book
    get a checkpoint first, dropped again when nothing changed."""
    _need(cid)
    args = dict(args or {})
    if op not in ("check", "fix", "toc", "toc_generate", "toc_save", "polish", "remove", "rename", "add"):
        raise EditError("No such tool")
    if op == "polish" and args.get("tool") not in TOOLS:
        raise EditError("No such tool")
    if op == "remove":
        args["names"] = [str(n) for n in args.get("names") or [] if str(n) not in _PROTECTED]
        if not args["names"]:
            raise EditError("Nothing to remove")
    if op == "rename":
        m = {str(a): str(b).strip().strip("/") for a, b in (args.get("map") or {}).items()}
        for a, b in m.items():
            _file(cid, a)
            _file(cid, b)
            if a in _PROTECTED or not b:
                raise EditError("That file keeps its name")
        args["map"] = m
    label = TOOLS.get(args.get("tool")) if op == "polish" else LABELS.get(op)
    with _lock(cid):
        n = checkpoint(cid, label) if label else None
        try:
            out = _run(cid, dict(args, op=op), timeout=900)
        except Exception:
            if n:
                _drop_checkpoint(cid, n)
            raise
        changed = out.get("changed", True) if op in ("polish", "fix") else op in LABELS or op == "toc_generate"
        if changed:
            _changed(cid)
        elif n:
            _drop_checkpoint(cid, n)
    return out


def add_file(cid, filename, data):
    """A file from the device into the book (beside the others of its kind)."""
    _need(cid)
    base = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", Path(str(filename or "")).name).strip(" .")
    if not base or "." not in base:
        raise EditError("A file name with its ending, like picture.jpg")
    if not data or len(data) > 100 * 1024 * 1024:
        raise EditError("A file of 100 MB or less")
    inbox = home(cid) / "incoming"
    inbox.mkdir(exist_ok=True)
    p = inbox / base
    p.write_bytes(data)
    try:
        return tool(cid, "add", {"name": base, "src": inside(p)})
    finally:
        p.unlink(missing_ok=True)


# ---------- Save ----------
def save(cid):
    """Builds the book from the working copy (Calibre) and puts it in Calibre in place of the
    format it came from (calibrewrite's add_format). The copy stays, now the same as Calibre's."""
    from . import calibrewrite as W
    m = _need(cid)
    fmt = m["fmt"]
    with _lock(cid):
        dest = home(cid) / ("out." + fmt.lower())
        try:
            _run(cid, {"op": "build", "fmt": fmt, "out": inside(dest)}, timeout=900)
            data = dest.read_bytes()
            W.run([{"op": "add_format", "id": int(cid), "fmt": fmt, "data": W.b64(data)}], timeout=600)
        except W.CalibreError as e:
            raise EditError(str(e))
        finally:
            dest.unlink(missing_ok=True)
        src = _source(cid, fmt)
        m.update(changed=False, saved=int(time.time()), src=_stamp(src) if src else m.get("src"))
        _put_meta(cid, m)
    return {"ok": True, "size": len(data), "format": fmt}
