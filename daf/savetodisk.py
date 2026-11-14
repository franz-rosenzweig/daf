"""Save to disk, the way Calibre does it (All books → Download with several books chosen, or
Library → Save to disk…): the chosen books in folders named by Calibre's save template (its default
is {author_sort}/{title}/{title} - {authors}), each with the formats asked for, its cover beside them
as <name>.jpg and its details as <name>.opf, all in one zip.

The names are Calibre's own. A short script runs Calibre's save_to_disk code inside Calibre-Web
Automated's container (get_path_components: its template language, its file-name rules, ASCII, the
underscores, lower case, a single folder, and its title-sort tweak, so "The X" is filed as "X, The")
and metadata_to_opf for the OPF. It works on a copy of metadata.db made with SQLite's backup from a
read-only connection, opened as a library of its own in a temporary folder, so Calibre's library is
only read. Daf then builds the zip here from the files in the library, checking every name again.

Calibre's "Update metadata in saved copies" and "Save data files as well" aren't here: the files
already carry their details (calibrewrite writes them in after every change), and the zip has the
books' files as Calibre keeps them.
"""
import json
import logging
import re
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path

from . import config
from . import calibrewrite as W
from .db import read_only

log = logging.getLogger("daf.savetodisk")

DEFAULT_TEMPLATE = "{author_sort}/{title}/{title} - {authors}"
DEFAULTS = {"template": DEFAULT_TEMPLATE, "formats": "all", "cover": True, "opf": True,
            "underscores": False, "ascii": False, "lowercase": False, "single": False}
# Calibre's room for a path: 1024 less 15 and the folder it saves into (save_to_disk.sanitize_args);
# a Mac's Downloads folder is about 40 long.
LENGTH = 1024 - 15 - 40
CAP = 200                      # bytes a folder or file name may have here (a Mac allows 255)
COVER_REF = "daf-cover-placeholder.jpg"

# Runs inside the container, in Calibre's own Python: the job on stdin, the answer after DAFRESULT.
SCRIPT = r'''
def main():
    import json, os, shutil, sqlite3, sys, tempfile, traceback
    job = json.loads(sys.stdin.read())
    tmp = tempfile.mkdtemp(prefix="daf-save-")
    out = {"ok": True, "books": {}, "errors": {}}
    try:
        src = sqlite3.connect("file:" + os.path.join(job["lib"], "metadata.db") + "?mode=ro", uri=True)
        dst = sqlite3.connect(os.path.join(tmp, "metadata.db"))
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.close()
        src.close()
        from calibre.library import db as _db
        from calibre.library.save_to_disk import config, get_path_components, preprocess_template
        from calibre.ebooks.metadata.opf2 import metadata_to_opf
        d = _db(tmp).new_api
        o = job["opts"]
        opts = config("").parse()
        opts.template = preprocess_template(o["template"])
        opts.asciiize, opts.replace_whitespace = bool(o["ascii"]), bool(o["underscores"])
        opts.to_lowercase, opts.single_dir = bool(o["lowercase"]), bool(o["single"])
        have, covers = set(d.all_book_ids()), set(job["covers"])
        for i in job["ids"]:
            if i not in have:
                out["errors"][str(i)] = "Calibre has no such book"
                continue
            mi = d.get_metadata(i)
            try:
                comps = get_path_components(opts, mi, i, job["length"])
            except Exception as e:
                out["errors"][str(i)] = str(e) or e.__class__.__name__
                continue
            opf = None
            if o["opf"]:
                mi.cover = job["cover_ref"] if o["cover"] and i in covers else None
                mi.cover_data = (None, None)
                opf = metadata_to_opf(mi)
                opf = opf.decode("utf-8") if isinstance(opf, bytes) else opf
            out["books"][str(i)] = {"components": list(comps), "opf": opf}
    except Exception as e:
        out = {"ok": False, "error": str(e) or e.__class__.__name__, "trace": traceback.format_exc()[-1500:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("DAFRESULT " + json.dumps(out))
main()
'''


def clean(b):
    """The sheet's options, checked, Calibre's defaults for anything missing."""
    b = b if isinstance(b, dict) else {}
    o = dict(DEFAULTS)
    t = b.get("template")
    if isinstance(t, str) and t.strip():
        o["template"] = t.strip()[:1000]
    f = b.get("formats")
    if isinstance(f, list):
        fs = list(dict.fromkeys(str(x).strip().upper() for x in f if re.fullmatch(r"[A-Za-z0-9_]{1,24}", str(x).strip())))
        o["formats"] = fs[:40] if fs else "all"
    for k in ("cover", "opf", "underscores", "ascii", "lowercase", "single"):
        if k in b:
            o[k] = bool(b[k])
    return o


def names(cids, covers, opts, timeout=300):
    """Calibre's names for the books: {calibre id: {components, opf}}, and {calibre id: error}."""
    job = {"lib": W.LIB, "ids": [int(i) for i in cids], "covers": [int(i) for i in covers], "opts": opts,
           "length": LENGTH, "cover_ref": COVER_REF}
    try:
        r = subprocess.run(W.RUN + [W.DEBUG, "-c", SCRIPT], input=json.dumps(job), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Calibre took too long")
    except OSError as e:
        raise RuntimeError(f"Couldn't reach Calibre: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        log.warning("calibre-debug said: %s %s", r.stdout[-800:], r.stderr[-800:])
        raise RuntimeError("Calibre didn't answer")
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        log.warning("save to disk: %s", out.get("trace"))
        raise RuntimeError(out.get("error") or "Calibre said no")
    return {int(k): v for k, v in out["books"].items()}, {int(k): v for k, v in out["errors"].items()}


_BAD = re.compile(r"[\x00-\x1f\x7f/\\]")


def part(s, cap=CAP):
    """One folder or file name, safe whatever Calibre made of the template: no slashes, no control
    characters, never "." or "..", no leading dot, at most `cap` bytes."""
    s = _BAD.sub("_", str(s or "")).strip()
    if s.startswith("."):
        s = "_" + s[1:]
    raw = s.encode("utf-8")
    if len(raw) > cap:
        s = raw[:cap].decode("utf-8", "ignore").rstrip()
    return s or "_"


def library(cids):
    """For each book, what the library has: {calibre id: {"dir": Path, "cover": Path|None, "files": {FMT: Path}}}."""
    db = config.CALIBRE_DBS[0]
    lib = db.parent
    c = read_only(db)
    try:
        q = (f"SELECT b.id, b.path, b.has_cover, d.format, d.name FROM books b LEFT JOIN data d ON d.book = b.id "
             f"WHERE b.id IN ({','.join('?' * len(cids))})")
        rows = c.execute(q, list(cids)).fetchall()
    finally:
        c.close()
    out = {}
    for bid, path, has_cover, fmt, name in rows:
        b = out.setdefault(bid, {"dir": lib / path, "cover": None, "files": {}})
        cov = lib / path / "cover.jpg"
        if has_cover and cov.is_file():
            b["cover"] = cov
        if fmt and name:
            p = lib / path / f"{name}.{fmt.lower()}"
            if p.is_file():
                b["files"][fmt.upper()] = p
    return out


def _xml_attr(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def layout(cids, opts, lib, named):
    """What goes in the zip, in the order chosen: ([(name in the zip, Path or text)], saved ids, {id: why not})."""
    entries, saved, skipped, used = [], [], {}, set()
    want = None if opts["formats"] == "all" else {f.upper() for f in opts["formats"]}
    for cid in cids:
        b, n = lib.get(cid), named.get(cid)
        if not b or not n:
            skipped[cid] = "Calibre has no such book"
            continue
        fmts = sorted(b["files"]) if want is None else sorted(want & set(b["files"]))
        if want is not None and not fmts:
            skipped[cid] = "Requested formats not available"          # Calibre's words
            continue
        cover = b["cover"] if opts["cover"] else None
        if not fmts and not opts["opf"] and not cover:
            skipped[cid] = "Nothing to save"
            continue
        comps = [part(x) for x in n["components"] if str(x).strip()] or [str(cid)]
        base, k = "/".join(comps), 2
        while base.casefold() in used:                                  # two books with one name (a Mac doesn't tell case apart)
            comps[-1] = part(f"{n['components'][-1]} ({k})") if n["components"] else f"{cid} ({k})"
            base, k = "/".join(comps), k + 1
        used.add(base.casefold())
        if cover:
            entries.append((base + ".jpg", cover))
        if opts["opf"] and n.get("opf"):
            opf = n["opf"].replace(f'href="{COVER_REF}"', f'href="{_xml_attr(comps[-1] + ".jpg")}"')
            entries.append((base + ".opf", opf))
        for f in fmts:
            entries.append((base + "." + f.lower(), b["files"][f]))
        saved.append(cid)
    return entries, saved, skipped


# ---------- the zip, kept until it's fetched (or an hour) ----------
_ready = {}
_lock = threading.Lock()


def _dir():
    return Path(config.STATE).parent


def build(cids, opts):
    """The zip for these books → {file, name, books, skipped}; fetched with ready(file)."""
    _sweep()
    lib = library(cids)
    named, errors = names(cids, [i for i, b in lib.items() if b["cover"]], opts)
    if not named and errors:
        raise RuntimeError(next(iter(errors.values())))
    entries, saved, skipped = layout(cids, opts, lib, named)
    if not saved:
        raise RuntimeError(next(iter(skipped.values()), "Nothing to save"))
    token = uuid.uuid4().hex[:16]
    path = _dir() / f"daf-save-{token}.zip"
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
            for name, src in entries:
                if isinstance(src, Path):
                    z.write(src, name)
                else:
                    z.writestr(zipfile.ZipInfo(name, time.localtime()[:6]), src.encode("utf-8"), zipfile.ZIP_DEFLATED)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    one = named[saved[0]]["components"]
    name = (part(one[-1], 120) if len(saved) == 1 and one else f"{len(saved)} books") + ".zip"
    with _lock:
        _ready[token] = (path, name, time.time())
    return {"file": token, "name": name, "books": len(saved), "skipped": sorted(skipped)}


def ready(token):
    """(path, name) of a zip made by build(), or (None, None)."""
    with _lock:
        r = _ready.get(token) if re.fullmatch(r"[0-9a-f]{16}", str(token)) else None
    return (r[0], r[1]) if r and r[0].exists() else (None, None)


def forget(token):
    with _lock:
        r = _ready.pop(token, None)
    if r:
        r[0].unlink(missing_ok=True)


def _sweep(age=3600):
    """Zips nobody fetched within the hour, and ones left from before a restart."""
    now = time.time()
    with _lock:
        for t in [t for t, r in _ready.items() if now - r[2] > age]:
            _ready.pop(t)[0].unlink(missing_ok=True)
        live = {r[0] for r in _ready.values()}
    try:
        for p in _dir().glob("daf-save-*.zip"):
            if p not in live and now - p.stat().st_mtime > age:
                p.unlink(missing_ok=True)
    except OSError:
        pass
