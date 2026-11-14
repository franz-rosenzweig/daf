"""Changes to the Calibre library, made by Calibre itself. Daf never writes metadata.db: each change
is a short script run with calibre-debug inside Calibre-Web Automated's container (DAF_CALIBRE_RUN),
using Calibre's own library API. So Calibre's rules hold: a new title or author moves the book's
folder, the sort fields follow, a removed book goes to Calibre's trash, a cover is resized the way
Calibre does it, and metadata.opf beside each book is written again.

One change at a time (a lock): Calibre-Web Automated's imports go through Calibre too, and SQLite
waits for whichever is first.

    DAF_CALIBRE_RUN   how to reach Calibre (default: docker exec -i -u abc -e CALIBRE_CONFIG_DIRECTORY=/config/.daf-calibre
                      calibre-web-automated: Daf's own Calibre settings and plugins, apart from the container's)
    DAF_CALIBRE_LIB   the library's path as Calibre sees it (default: /calibre-library)
"""
import base64
import json
import logging
import os
import shlex
import subprocess
import threading
import time
import uuid

from . import config

log = logging.getLogger("daf.calibrewrite")
RUN = shlex.split(os.environ.get("DAF_CALIBRE_RUN", "docker exec -i -u abc -e CALIBRE_CONFIG_DIRECTORY=/config/.daf-calibre calibre-web-automated"))
LIB = os.environ.get("DAF_CALIBRE_LIB", "/calibre-library")
DEBUG = "/app/calibre/calibre-debug"
_lock = threading.Lock()

# Runs inside the container, in Calibre's own Python. The job comes on stdin as JSON, the answer goes
# back on the last line of stdout after DAFRESULT.
SCRIPT = r'''
def main():
    import base64, json, os, subprocess, sys, tempfile, traceback
    from calibre.library import db as _db
    from datetime import datetime, timezone
    from calibre.utils.date import UNDEFINED_DATE
    def day(v):                                     # a date alone: noon UTC, the same day everywhere
        y, m, dd = (int(x) for x in str(v)[:10].split("-"))
        return datetime(y, m, dd, 12, 0, tzinfo=timezone.utc)
    def _check_template(tpl):                       # Calibre's own formatter tries it on a made-up book first
        from calibre.ebooks.metadata.book.base import Metadata
        from calibre.ebooks.metadata.book.formatter import SafeFormat
        mi = Metadata("Title", ["Author"])
        r = SafeFormat().safe_format(tpl, mi, "TEMPLATE ERROR", mi)
        if str(r).startswith("TEMPLATE ERROR"):
            raise ValueError("The template: " + str(r)[14:].strip()[:200])
    job = json.loads(sys.stdin.read())
    ldb = _db(job["lib"])
    d = ldb.new_api
    touched, out = set(), {"ok": True, "books": {}, "done": []}
    def val(field, v):
        fm = d.field_metadata[field]
        dt = fm.get("datatype")
        if v is None or v == "" or v == []:
            return None if dt not in ("text",) or not fm.get("is_multiple") else ()
        if field == "rating" or dt == "rating":
            return max(0, min(10, int(round(float(v) * 2))))
        if dt == "datetime":
            return day(v) if v else UNDEFINED_DATE
        if dt == "int":
            return int(float(v))
        if dt == "float":
            return float(v)
        if dt == "enumeration" and str(v) not in (fm.get("display") or {}).get("enum_values", []):
            raise ValueError("“%s” isn't one of %s's choices" % (v, fm.get("name") or field))
        if dt == "bool":
            return bool(v) if not isinstance(v, str) else v.lower() in ("true", "yes", "1")
        if field == "identifiers":
            return {str(k).strip().lower(): str(x).strip() for k, x in dict(v).items() if str(k).strip() and str(x).strip()}
        if field in ("authors", "tags", "languages") or fm.get("is_multiple"):
            return tuple(str(x).strip() for x in (v if isinstance(v, (list, tuple)) else str(v).split(",")) if str(x).strip())
        if field == "series_index":
            return float(v)
        return str(v)
    try:
        for op in job["ops"]:
            k = op["op"]
            ids = [int(i) for i in op.get("ids") or ([op["id"]] if "id" in op else [])]
            have = set(d.all_book_ids())
            missing = [i for i in ids if i not in have]
            if missing and k != "embed":
                raise ValueError("Calibre has no book %s" % missing[0])
            if k == "set":
                for field, v in op["fields"].items():
                    if field == "pubdate":
                        v = day(v) if v else UNDEFINED_DATE
                        d.set_field("pubdate", {i: v for i in ids})
                        continue
                    if field == "authors_flip":             # "Last, First" → "First Last", each book its own
                        import re as _re
                        def flip(a):
                            m = _re.fullmatch(r"\s*([^,]+),\s*([^,]+?)\s*", a)
                            if not m or _re.search(r"(?i)\b(inc|ltd|llc|co|corp|press|services|ph\.?\s?d|m\.?d|jr|sr|ii|iii|iv)\.?$", m.group(2)):
                                return a
                            return m.group(2) + " " + m.group(1)
                        new = {}
                        for i in ids:
                            cur = d.field_for("authors", i)
                            nxt = tuple(flip(a) for a in cur)
                            if nxt != cur:
                                new[i] = nxt
                        if new:
                            d.set_field("authors", new)
                        continue
                    if field == "series_number":            # 1, 2, 3… in the order given
                        start = float(v or 1)
                        d.set_field("series_index", {i: start + n for n, i in enumerate(ids)})
                        continue
                    v = val(field, v)
                    if field == "authors" and not v:
                        v = ("Unknown",)
                    if field == "title" and not v:
                        raise ValueError("A book needs a title")
                    d.set_field(field, {i: v for i in ids})
            elif k == "tags":
                add = [t.strip() for t in op.get("add") or [] if t.strip()]
                rem = {t.strip().lower() for t in op.get("remove") or []}
                new = {}
                for i in ids:
                    cur = [t for t in d.field_for("tags", i) if t.lower() not in rem]
                    for t in add:
                        if t.lower() not in {x.lower() for x in cur}:
                            cur.append(t)
                    new[i] = tuple(cur)
                d.set_field("tags", new)
            elif k == "cover":
                data = base64.b64decode(op["data"]) if op.get("data") else None
                d.set_cover({ids[0]: data})
            elif k in ("create_column", "column_heading", "column_template", "delete_column"):    # Calibre's Add your own columns
                import re as _re
                label = str(op["label"]).strip().lower()
                cols = ldb.custom_column_label_map
                if k == "create_column":
                    if not _re.fullmatch(r"[a-z][a-z0-9_]{0,39}", label):
                        raise ValueError("A lookup name is lower-case letters, digits and _, and starts with a letter")
                    if label in cols or label in d.field_metadata.keys() or ("#" + label) in d.field_metadata.keys():
                        raise ValueError("There's a column called %s already" % label)
                    if op["datatype"] == "composite":
                        _check_template(op["display"]["composite_template"])
                    ldb.create_custom_column(label, str(op["heading"]).strip(), op["datatype"], bool(op.get("multiple")), editable=op["datatype"] != "composite", display=op.get("display") or {})
                else:
                    if label not in cols:
                        raise ValueError("Calibre has no column %s" % label)
                    if k == "column_heading":
                        ldb.set_custom_column_metadata(cols[label]["num"], name=str(op["heading"]).strip())
                    elif k == "column_template":
                        if cols[label]["datatype"] != "composite":
                            raise ValueError("Only a column built from other columns has a template")
                        _check_template(op["template"])
                        ldb.set_custom_column_metadata(cols[label]["num"], display=dict(cols[label]["display"] or {}, composite_template=op["template"]))
                    else:
                        ldb.delete_custom_column(label=label)      # gone for good the next time Calibre opens the library
                        _db(job["lib"])                            # which is now
                out["done"].append(k)
                continue
            elif k == "author_meta":                    # Calibre's Manage authors: an author's sort and link
                from calibre.ebooks.metadata import author_to_author_sort
                name = str(op["name"])
                amap = {n: i for i, n in d.get_id_map("authors").items()}
                aid = amap.get(name, amap.get(name.replace(",", "|")))
                if aid is None:
                    raise ValueError("Calibre has no author %s" % name)
                if "sort" in op:
                    d.set_sort_for_authors({aid: str(op["sort"]).strip() or author_to_author_sort(name.replace("|", ","))})
                if "link" in op:
                    d.set_link_for_authors({aid: str(op["link"]).strip()})
                touched.update(d.books_for_field("authors", aid))
                out["done"].append(k)
                continue
            elif k == "drop":                           # books dropped on a name in the Tag browser, as Calibre's handle_drop does it
                key, v = op["field"], op["value"]
                fm = d.field_metadata[key]
                if key == "authors":
                    d.set_field("authors", {i: (v,) for i in ids})
                elif fm["datatype"] == "rating":
                    d.set_field(key, {i: int(round(float(v) * 2)) for i in ids})
                elif fm["datatype"] == "series":         # the series, each book the next number in it
                    for i in ids:
                        n = d.get_next_series_num_for(v, field=key)
                        d.set_field(key, {i: v})
                        d.set_field("series_index" if key == "series" else key + "_index", {i: n})
                elif fm["is_multiple"]:
                    d.set_field(key, {i: tuple(list(d.field_for(key, i)) + ([] if v in d.field_for(key, i) else [v])) for i in ids})
                else:
                    d.set_field(key, {i: v for i in ids})
            elif k == "trim_cover":                     # Calibre's Trim: the cover's plain borders cut off
                from calibre.utils.img import remove_borders_from_image, image_from_data, image_to_data
                data = d.cover(ids[0])
                if not data:
                    raise ValueError("The book has no cover")
                d.set_cover({ids[0]: image_to_data(remove_borders_from_image(image_from_data(data)), fmt="JPEG")})
            elif k == "remove_covers":                  # Calibre's Remove cover (and "Remove all covers" in bulk)
                d.set_cover({i: None for i in ids})
            elif k == "gencover":                       # Calibre's own generated cover (Generate cover; Edit metadata in bulk's "Generate default cover")
                os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
                from calibre.ebooks.covers import generate_cover
                for i in ids:
                    d.set_cover({i: generate_cover(d.get_metadata(i))})
            elif k == "add_format":
                fmt = op["fmt"].upper()
                with tempfile.NamedTemporaryFile(suffix="." + fmt.lower(), delete=False) as f:
                    f.write(base64.b64decode(op["data"]))
                try:
                    d.add_format(ids[0], fmt, f.name, replace=True)
                finally:
                    os.unlink(f.name)
            elif k == "remove_formats":
                d.remove_formats({ids[0]: [x.upper() for x in op["fmts"]]})
            elif k == "annotations":                    # Daf's highlights for Calibre's viewer, merged as the viewer saves its own (calibreannots.py)
                d.merge_annotations_for_book(ids[0], op["fmt"].upper(), op["annots"], user_type="local", user="viewer")
            elif k == "convert":
                import shutil
                src = d.format_abspath(ids[0], op["from"].upper())
                if not src:
                    raise ValueError("The book has no %s file" % op["from"].upper())
                flags = op.get("flags") or []
                if not all(isinstance(f, str) and f.startswith("--") for f in flags):
                    raise ValueError("bad conversion flags")
                if op.get("save") is not None:          # the Convert sheet's settings become the book's own, as Calibre's dialog keeps them
                    from calibre.ebooks.conversion.config import load_specifics, save_specifics
                    recs = load_specifics(ldb, ids[0])
                    recs.update(op["save"])
                    recs["gui_preferred_input_format"] = op["from"].lower()
                    save_specifics(ldb, ids[0], recs)
                tmp = tempfile.mkdtemp(prefix="daf-convert-")
                try:
                    dst = os.path.join(tmp, "book." + op["to"].lower())
                    cmd = ["/app/calibre/ebook-convert", src, dst] + flags
                    if op.get("css"):                   # extra CSS as a file, so its text is never taken for a path
                        css = os.path.join(tmp, "extra.css")
                        with open(css, "w", encoding="utf-8") as f:
                            f.write(op["css"])
                        cmd.append("--extra-css=" + css)
                    if op.get("sr"):                    # Search & replace: a regex line, then its replacement line
                        pairs = op["sr"]
                        if not all(isinstance(x, list) and len(x) == 2 and all(isinstance(y, str) and not any(c in y for c in "\r\n") for y in x) for x in pairs):
                            raise ValueError("bad search and replace")
                        srf = os.path.join(tmp, "search-replace.txt")
                        with open(srf, "w", encoding="utf-8") as f:
                            f.write("".join(a + "\n" + b + "\n" for a, b in pairs))
                        cmd.append("--search-replace=" + srf)
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
                    if r.returncode or not os.path.exists(dst):
                        raise ValueError("Calibre couldn't convert it: " + (r.stderr or r.stdout or "")[-400:])
                    d.add_format(ids[0], op["to"].upper(), dst, replace=True)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            elif k == "merge":                          # the others' files, tags, identifiers and empty fields into one; then the others go
                keep = int(op["keep"])
                others = [i for i in ids if i != keep]
                for o in others:
                    have = {f.upper() for f in d.formats(keep)}
                    for fmt in d.formats(o):
                        if fmt.upper() not in have:
                            d.add_format(keep, fmt, d.format_abspath(o, fmt), replace=False)
                    tags = list(d.field_for("tags", keep))
                    for t in d.field_for("tags", o):
                        if t.lower() not in {x.lower() for x in tags}:
                            tags.append(t)
                    d.set_field("tags", {keep: tuple(tags)})
                    idk = dict(d.field_for("identifiers", keep))
                    for a, b in d.field_for("identifiers", o).items():
                        idk.setdefault(a, b)
                    d.set_field("identifiers", {keep: idk})
                    for f in ["series", "publisher", "rating", "comments", "languages"] + sorted(d.field_metadata.custom_field_keys()):
                        if d.field_metadata[f].get("datatype") == "composite":
                            continue
                        if not d.field_for(f, keep) and d.field_for(f, o):
                            d.set_field(f, {keep: d.field_for(f, o)})
                            if f == "series":
                                d.set_field("series_index", {keep: d.field_for("series_index", o)})
                    if d.field_for("pubdate", keep) == UNDEFINED_DATE and d.field_for("pubdate", o) != UNDEFINED_DATE:
                        d.set_field("pubdate", {keep: d.field_for("pubdate", o)})
                    if not d.field_for("cover", keep) and d.field_for("cover", o):
                        d.set_cover({keep: d.cover(o)})
                d.remove_books(others)
                for o in others:
                    out["books"][str(o)] = None
                touched.add(keep)
                out["done"].append(k)
                continue
            elif k == "trash":                          # what Calibre's trash holds
                books, _fmts = d.list_trash_entries()
                out["trash"] = [{"id": e.book_id, "title": e.title, "author": e.author, "removed": int(e.mtime)} for e in books]
                out["done"].append(k)
                continue
            elif k == "restore":
                for i in [int(x) for x in op["trash_ids"]]:
                    d.move_book_from_trash(i)
                    touched.add(i)
                out["done"].append(k)
                continue
            elif k in ("rename_items", "remove_items"):    # a tag, author, series… across the library
                field = op["field"]
                names = op["renames"] if k == "rename_items" else {n: None for n in op["names"]}
                ids_map, hit = {}, set()
                exact = {n: i for i, n in d.get_id_map(field).items()}
                for name, to in names.items():
                    iid = exact.get(name)       # get_item_id(case_sensitive=True) misses names with a comma
                    if iid is None and field == "authors":
                        iid = exact.get(name.replace(",", "|"))     # Calibre keeps an author's comma as |
                    if iid is None:
                        continue
                    hit |= set(d.books_for_field(field, iid))
                    if to is None or to != name:
                        ids_map[iid] = to
                if not ids_map:
                    raise ValueError("Calibre has none of those names")
                if ids_map:
                    if k == "rename_items":
                        d.rename_items(field, ids_map)
                    else:
                        d.remove_items(field, list(ids_map))
                touched.update(hit)
                out["done"].append(k)
                continue
            elif k == "embed":                          # the details into the book files themselves
                d.embed_metadata([i for i in ids if i in have])
                out["done"].append(k)
                continue
            elif k == "remove_books":
                d.remove_books(ids)
                for i in ids:
                    out["books"][str(i)] = None
                out["done"].append(k)
                continue
            elif k == "add_empty":                      # books with no file, as Calibre's Add empty book makes them
                from calibre.ebooks.metadata.book.base import Metadata
                todo = []
                for b in op["books"]:                   # every value checked before the first book is made
                    extra = {f: val(f, v) for f, v in (b.get("fields") or {}).items()}
                    todo.append((b, extra))
                added = []
                for b, extra in todo:
                    mi = Metadata(str(b.get("title") or "").strip() or "Unknown", list(val("authors", b.get("authors") or [])) or ["Unknown"])
                    if b.get("series"):
                        mi.series = str(b["series"]).strip()
                        mi.series_index = float(b["series_index"]) if b.get("series_index") not in (None, "") else None
                    if b.get("pubdate"):
                        mi.pubdate = day(b["pubdate"])
                    if b.get("identifiers"):
                        mi.set_identifiers(val("identifiers", b["identifiers"]))
                    if b.get("tags"):
                        mi.tags = list(val("tags", b["tags"]))
                    i = d.create_book_entry(mi)         # Calibre's own: the folder, the sorts, its new-book tags
                    for f, v in extra.items():
                        d.set_field(f, {i: v})
                    added.append(i)
                    touched.add(i)
                out["added"] = added
                out["done"].append(k)
                continue
            elif k == "epubmerge":                      # EpubMerge (the plugin): the books' EPUBs, in this order, into one new book
                import shutil
                import calibre.customize.ui             # noqa: F401 - loads the plugins, so calibre_plugins.* imports
                from calibre_plugins.epubmerge.epubmerge import doMerge
                from calibre.ebooks.metadata.meta import set_metadata
                if len(ids) < 2:
                    raise ValueError("Two books or more")
                tdir = tempfile.mkdtemp(prefix="daf-epubmerge-")
                nid = None
                try:
                    books, epubs = [], []
                    for n, i in enumerate(ids):
                        mi = d.get_metadata(i)
                        if not d.has_format(i, "EPUB"):
                            raise ValueError("%s has no EPUB" % mi.title)
                        p = os.path.join(tdir, "input_%d_%d.epub" % (n, i))
                        d.copy_format_to(i, "EPUB", p)
                        with open(p, "r+b") as f:       # each book's details inside it, as the plugin keeps them
                            set_metadata(f, mi, stream_type="epub")
                        books.append(mi)
                        epubs.append(p)
                    word = "Anthology"
                    title = str(op.get("title") or "").strip()
                    if not title:                       # the plugin's: the series, when every book is in the same one
                        series = {b.series for b in books}
                        title = books[0].series if len(series) == 1 and books[0].series else "%s %s" % (books[0].title, word)
                    authors = list(val("authors", op.get("authors") or []))
                    if not authors:
                        for b in books:
                            authors += [a for a in b.authors if a not in authors]
                    from calibre.ebooks.metadata.book.base import Metadata
                    mi = Metadata(title, authors or ["Unknown"])
                    pubs = {b.publisher for b in books}
                    if len(pubs) == 1:
                        mi.publisher = pubs.pop()
                    mi.tags = list(dict.fromkeys(t for b in books for t in (b.tags or [])))
                    mi.languages = list(dict.fromkeys(l for b in books for l in (b.languages or [])))
                    many = len(authors) > 1
                    name = lambda b: "%s by %s" % (b.title, " & ".join(b.authors)) if many else b.title
                    esc = lambda s: str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    mi.comments = "<p>%s containing:</p>" % word
                    if op.get("descriptions"):
                        mi.comments += '<div class="mergedbook">' + '<hr></div><div class="mergedbook">'.join(
                            ("<p><b>%s</b></p>%s" % (esc(name(b)), b.comments)) if b.comments else "<b>%s</b><br/>" % esc(name(b)) for b in books) + "</div>"
                    else:
                        mi.comments += "<br/>".join(esc(name(b)) for b in books)
                    nid = d.create_book_entry(mi, add_duplicates=True)
                    cover = d.cover(ids[0])             # the first book's cover, as the plugin does
                    if cover:
                        d.set_cover({nid: cover})
                    nmi = d.get_metadata(nid)
                    cpath = os.path.join(job["lib"], d.field_for("path", nid), "cover.jpg") if cover else None
                    dst = os.path.join(tdir, "merged.epub")
                    doMerge(dst, epubs, authoropts=list(nmi.authors), titleopt=nmi.title, descopt=nmi.comments,
                            tags=list(nmi.tags or []), languages=list(nmi.languages or []) or ["en"],
                            titlenavpoints=True, originalnavpoints=True, keepsingletocs=False,
                            flattentoc=bool(op.get("flatten")), printtimes=False,
                            coverjpgpath=cpath if cpath and os.path.exists(cpath) else None, keepmetadatafiles=True)
                    d.add_format(nid, "EPUB", dst)
                except Exception:
                    if nid is not None:                 # no half-made book left behind
                        d.remove_books([nid], permanent=True)
                    raise
                finally:
                    shutil.rmtree(tdir, ignore_errors=True)
                out["added"] = [nid]
                touched.add(nid)
                out["done"].append(k)
                continue
            elif k == "polish":                         # Polish books (Calibre's toolbar action), as its dialog and gui_polish job do it
                import shutil
                from calibre.ebooks.metadata.opf2 import metadata_to_opf
                from calibre.ebooks.oeb.polish.main import SUPPORTED, gui_polish
                i = ids[0]
                acts = ("embed", "subset", "smarten_punctuation", "metadata", "do_cover", "jacket", "remove_jacket",
                        "remove_unused_css", "compress_images", "download_external_resources", "add_soft_hyphens",
                        "remove_soft_hyphens", "upgrade_book")
                data = {a: bool((op.get("opts") or {}).get(a)) for a in acts}
                if data["jacket"]:
                    data["metadata"] = True             # the dialog won't add a jacket without the details
                if not any(data.values()):
                    raise ValueError("Nothing to do")
                have_f = {f.upper() for f in d.formats(i) or ()}
                # Every EPUB, AZW3 and KEPUB the book has, each from its ORIGINAL_ when there is one
                todo = [(f, "ORIGINAL_" + f if "ORIGINAL_" + f in have_f else f) for f in ("EPUB", "AZW3", "KEPUB")
                        if f in SUPPORTED and (f in have_f or "ORIGINAL_" + f in have_f)]
                if not todo:
                    raise ValueError("No EPUB, AZW3 or KEPUB")
                base = tempfile.mkdtemp(prefix="daf-polish-")
                try:
                    mi = d.get_metadata(i)              # create_opf_file: the book's details, without the cover
                    mi.cover = None
                    mi.application_id = mi.uuid
                    opf = os.path.join(base, "metadata.opf")
                    with open(opf, "wb") as f:
                        f.write(metadata_to_opf(mi))
                    data.update(opf=opf, files=[])
                    cover = os.path.join(base, "cover.jpg")
                    if d.copy_cover_to(i, cover):
                        data["cover"] = cover
                    for fmt, src in todo:
                        p = os.path.join(base, "%d.%s" % (i, fmt.lower()))
                        d.copy_format_to(i, src, p)
                        data["files"].append(p)
                    gui_polish(data)                    # every copy polished before any goes back: a failure leaves the book as it was
                    for fmt, src in todo:
                        if op.get("keep_original") and src == fmt:
                            d.save_original_format(i, fmt)
                        d.add_format(i, fmt, os.path.join(base, "%d.%s" % (i, fmt.lower())), replace=True, run_hooks=False)
                finally:
                    shutil.rmtree(base, ignore_errors=True)
                out["polished"] = [f for f, _s in todo]
            elif k == "restore_original":               # Calibre's Restore the ORIGINAL_<fmt> format: each original back as its format, the ORIGINAL_ gone
                import shutil
                i = ids[0]
                have_f = {f.upper() for f in d.formats(i) or ()}
                want = {str(f).upper() for f in op.get("fmts") or []}
                origs = sorted(f for f in have_f if f.startswith("ORIGINAL_") and (not want or f in want or f[9:] in want))
                if not origs:
                    raise ValueError("No ORIGINAL_ file to restore")
                for f in origs:                         # every original there before anything changes
                    p = d.format_abspath(i, f)
                    if not p or not os.path.exists(p):
                        raise ValueError("Calibre can't find the %s file" % f)
                tdir = tempfile.mkdtemp(prefix="daf-restore-")
                try:
                    backup = {}                         # the files there now, to put back if a restore fails
                    for f in origs:
                        if f[9:] in have_f:
                            backup[f[9:]] = os.path.join(tdir, "%d.%s" % (i, f[9:].lower()))
                            d.copy_format_to(i, f[9:], backup[f[9:]])
                    try:
                        for f in origs:
                            if not d.restore_original_format(i, f):
                                raise ValueError("Calibre couldn't restore %s" % f)
                    except Exception:
                        for f in origs:                 # back as it was: a restored original saved again, the file that was there put back
                            fmt, now = f[9:], {x.upper() for x in d.formats(i) or ()}
                            if f not in now and fmt in now:
                                d.save_original_format(i, fmt)
                            if fmt in backup:
                                d.add_format(i, fmt, backup[fmt], replace=True, run_hooks=False)
                            elif fmt in now:
                                d.remove_formats({i: [fmt]})
                        raise
                finally:
                    shutil.rmtree(tdir, ignore_errors=True)
                out["restored"] = origs
            else:
                raise ValueError("unknown op " + k)
            touched.update(ids)
            out["done"].append(k)
        for i in touched:
            if i in set(d.all_book_ids()):
                out["books"][str(i)] = {"title": d.field_for("title", i), "authors": list(d.field_for("authors", i)),
                                        "path": d.field_for("path", i), "has_cover": bool(d.field_for("cover", i))}
        try:
            d.dump_metadata()
        except Exception:
            pass
    except Exception as e:
        out = {"ok": False, "error": str(e) or e.__class__.__name__, "trace": traceback.format_exc()[-1500:]}
    print("DAFRESULT " + json.dumps(out))
main()
'''


class CalibreError(RuntimeError):
    pass


def run(ops, timeout=120):
    """Hands the changes to Calibre and waits. Returns {calibre id: {title, authors, path, has_cover}
    | None (removed)} and brings Daf's own book rows along."""
    job = json.dumps({"lib": LIB, "ops": ops})
    with _lock:
        try:
            r = subprocess.run(RUN + [DEBUG, "-c", SCRIPT], input=job, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise CalibreError("Calibre took too long")
        except OSError as e:
            raise CalibreError(f"Couldn't reach Calibre: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        log.warning("calibre-debug said: %s %s", r.stdout[-800:], r.stderr[-800:])
        raise CalibreError("Calibre didn't answer" + (": " + r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""))
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        log.warning("calibre change failed: %s", out.get("trace"))
        raise CalibreError(out.get("error") or "Calibre said no")
    books = {int(k): v for k, v in out["books"].items()}
    _follow(books)
    if any(op.get("op") in EMBED_AFTER for op in ops):
        embed_later([i for i, b in books.items() if b])
    if "trash" in out:
        books["trash"] = out["trash"]
    if "added" in out:                              # add_empty's new books, in the order given
        books["added"] = out["added"]
    return books


def _follow(books):
    """Daf's books rows for the books Calibre just changed: their title, author and folder (the
    cover is served from it), so the book page and the covers are right before the next sync."""
    from .db import connect
    conn = connect()
    try:
        for cid, b in books.items():
            if b is None:
                continue
            path = str(config.CALIBRE_DBS[0].parent / b["path"]) if b["has_cover"] else None
            conn.execute("UPDATE books SET title = ?, author = ?, calibre_path = ? WHERE calibre_id = ?",
                         (b["title"], " & ".join(b["authors"]) or None, path, cid))
        conn.commit()
    finally:
        conn.close()


def b64(data):
    return base64.b64encode(data).decode()


# ---------- the details go into the book files too, a little later ----------
# Calibre keeps a book's details in its database; the EPUB (or AZW3, PDF…) keeps its own copy inside,
# which is what the Kindle and other readers show. After a change, Calibre writes them into the
# files (embed_metadata), as Calibre-Web Automated does after an edit there. In the background, a
# batch at a time, so an edit of many books doesn't wait for it.
EMBED_AFTER = {"set", "tags", "cover", "gencover", "remove_covers", "drop", "trim_cover", "merge", "rename_items", "remove_items", "restore"}
_embed = {"pending": set(), "running": 0, "done": 0, "error": None}
_embed_cv = threading.Condition()


def embed_later(ids):
    with _embed_cv:
        _embed["pending"].update(int(i) for i in ids)
        _embed_cv.notify()
    _embed_worker()


def embed_status():
    return {"pending": len(_embed["pending"]) + _embed["running"], "done": _embed["done"], "error": _embed["error"]}


_worker = []


def _embed_worker():
    if _worker and _worker[0].is_alive():
        return

    def loop():
        while True:
            with _embed_cv:
                while not _embed["pending"]:
                    _embed_cv.wait(60)
                batch = sorted(_embed["pending"])[:25]
                _embed["pending"].difference_update(batch)
                _embed["running"] = len(batch)
            time.sleep(3)                       # an edit right after usually touches the same books
            r = None
            if _lock.acquire(timeout=900):
                try:
                    r = subprocess.run(RUN + [DEBUG, "-c", SCRIPT], input=json.dumps({"lib": LIB, "ops": [{"op": "embed", "ids": batch}]}),
                                       capture_output=True, text=True, timeout=900)
                except (subprocess.TimeoutExpired, OSError) as e:
                    log.warning("embed: %s", e)
                finally:
                    _lock.release()
            ok = r is not None and any(x.startswith("DAFRESULT ") and '"ok": true' in x for x in r.stdout.splitlines())
            _embed["error"] = None if ok else "Calibre couldn't write the details into some files"
            if not ok:
                log.warning("embed failed: %s", (r.stdout[-400:] + r.stderr[-400:]) if r else "lock")
            _embed["done"] += len(batch) if ok else 0
            _embed["running"] = 0
    t = threading.Thread(target=loop, daemon=True, name="calibre-embed")
    _worker[:] = [t]
    t.start()


# ---------- conversions take a while: a job the page asks about ----------
# Every job is a dict in _jobs that its own page polls (GET /api/catalog/jobs/{id}), in one of two
# shapes: {running, done, error} (start_job, start_each) or {state: running|done|failed, error}. The
# ones a person started on books also get a name (name()), and those make the Jobs list (Calibre's
# "Jobs" corner, jobs_list()); start_each's can be stopped between books (stop()).
_jobs = {}
DAY = 86400


def convert_op(cid, src, to, opts=None):
    """The convert op for one book. With the Convert sheet's options (convertopts.clean'd): ebook-convert's
    flags, the extra CSS and Search & replace (written to files in the container) and what the book
    keeps in Calibre."""
    op = {"op": "convert", "id": cid, "from": src, "to": to}
    if opts is not None:
        from . import convertopts
        op.update(flags=convertopts.flags(opts, to), save=convertopts.to_save(opts, to), **convertopts.files(opts))
    return op


def start_convert(cid, src, to, opts=None):
    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"state": "running", "started": time.time(), "id": cid, "to": to.upper()}

    def work():
        try:
            run([convert_op(cid, src, to, opts)], timeout=1000)
            _jobs[jid].update(state="done", ended=time.time())
        except Exception as e:  # noqa: BLE001 - the page says what went wrong
            _jobs[jid].update(state="failed", error=str(e), ended=time.time())
        finished(jid)
    threading.Thread(target=work, daemon=True).start()
    _prune()
    return jid


def start_job(fn, stoppable=False):
    """Any slow change as a job: {running, done (what fn returned), error}. A stoppable one's fn gets
    a stop() to ask between its steps: True once Stop was pressed (and the job then says stopped)."""
    jid = uuid.uuid4().hex[:12]
    j = _jobs[jid] = {"running": True, "started": time.time(), **({"stoppable": True} if stoppable else {})}

    def stop_now():
        if j.get("stop"):
            j["stopped"] = True
            return True
        return False

    def work():
        try:
            j["done"] = fn(stop_now) if stoppable else fn()
        except Exception as e:  # noqa: BLE001 - the page says what went wrong
            j["error"] = str(e)[:300]
        j["ended"] = time.time()
        j["running"] = False
        finished(jid)
    threading.Thread(target=work, daemon=True).start()
    _prune()
    return jid


def start_each(ops, timeout=1000, **info):
    """One op a book, one after another, each its own run, in one job: {running, done, total,
    failed: [{id, error}], **info}. Stop (stop()) takes effect between books: the one going on
    finishes, the rest are left, and the job says stopped."""
    jid = uuid.uuid4().hex[:12]
    j = _jobs[jid] = {"running": True, "started": time.time(), "done": 0, "total": len(ops), "failed": [], "stoppable": True, **info}

    def work():
        for op in ops:
            if j.get("stop"):
                j["stopped"] = True
                break
            try:
                run([op], timeout=timeout)
            except Exception as e:  # noqa: BLE001 - one book's failure doesn't stop the rest
                j["failed"].append({"id": op.get("id"), "error": str(e)[:300]})
            j["done"] += 1
        j["ended"] = time.time()
        j["running"] = False
        finished(jid)
    threading.Thread(target=work, daemon=True).start()
    _prune()
    return jid


def start_convert_many(todo, to, opts=None):
    """[(cid, from)] into `to`, one after another, in one job: {running, done, total, failed: [{id, error}]}.
    With the Convert sheet's options, every book gets the same ones, and keeps them in Calibre (Calibre's
    bulk convert does the same)."""
    return start_each([convert_op(cid, src, to, opts) for cid, src in todo], 1000, to=to)


def start_polish_many(ids, opts, keep_original):
    """Polish books (the "polish" op) for each book, one after another, in one job like start_convert_many's."""
    return start_each([{"op": "polish", "id": cid, "opts": opts, "keep_original": bool(keep_original)} for cid in ids], 1800)


def start_restore_many(ids):
    """Every ORIGINAL_ file of each book back in place of its format (the "restore_original" op), one book a run."""
    return start_each([{"op": "restore_original", "id": cid} for cid in ids], 600)


def job(jid):
    return _jobs.get(jid)


def _running(j):
    return bool(j.get("running")) if "running" in j else j.get("state") == "running"


def _prune():
    """Finished jobs go a day after they ended; one that never says it finished, after two."""
    now = time.time()
    for k, j in list(_jobs.items()):
        if (not _running(j) and now - (j.get("ended") or j["started"]) > DAY) or now - j["started"] > 2 * DAY:
            _jobs.pop(k, None)


def _row(jid, j):
    """A job as the Jobs list keeps it, its label still to be made (name)."""
    run_ = _running(j)
    fails = j.get("failed") if isinstance(j.get("failed"), list) else []
    if j.get("stopped"):
        state = "stopped"
    elif run_:
        state = "running"
    elif j.get("state") == "failed" or j.get("error") or (fails and len(fails) >= (j.get("total") or 0)):
        state = "failed"
    else:
        state = "done"
    counts = isinstance(j.get("done"), int) and not isinstance(j.get("done"), bool) and isinstance(j.get("total"), int)
    return {"id": jid, "kind": j.get("kind"), "name": j["name"], "state": state, "started": j["started"],
            "ended": None if run_ else j.get("ended"), "done": j["done"] if counts else None,
            "total": j["total"] if counts else None, "failed": len(fails),
            "errors": [{"id": f.get("id"), "error": f.get("error")} for f in fails[:5] if isinstance(f, dict)],
            "error": j.get("error") or (fails[0].get("error") if state == "failed" and fails and isinstance(fails[0], dict) else None)}


# The named jobs' rows are kept in Daf's own database too (kv calibre_jobs, {id: row}), written when a
# job is named and when it finishes, so the list survives a restart; one that was still running then
# shows as interrupted. Read once, then kept here.
_stored = None
_store_lock = threading.Lock()


def _store_load():
    from .db import connect
    conn = connect()
    try:
        r = conn.execute("SELECT v FROM kv WHERE k = 'calibre_jobs'").fetchone()
    finally:
        conn.close()
    v = json.loads(r[0]) if r and r[0] else {}
    return v if isinstance(v, dict) else {}


def _store_save(rows):
    from .db import connect
    conn = connect()
    try:
        conn.execute("INSERT INTO kv (k, v) VALUES ('calibre_jobs', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v", (json.dumps(rows),))
        conn.commit()
    finally:
        conn.close()


def _keep(r, now):
    """A stored row still worth keeping: finished less than a day ago, started less than two."""
    return now - (r.get("ended") or r.get("started") or 0) <= DAY and now - (r.get("started") or 0) <= 2 * DAY


def stored():
    """The kept rows, {id: row}: read from the database the first time."""
    global _stored
    with _store_lock:
        if _stored is None:
            try:
                _stored = _store_load()
            except Exception as e:  # noqa: BLE001 - no kept rows is still a list
                log.warning("jobs: couldn't read the kept ones: %s", e)
                _stored = {}
        return _stored


def _store(jid):
    j = _jobs.get(jid)
    if not j or not j.get("name"):
        return
    rows = stored()
    with _store_lock:
        now = time.time()
        rows[jid] = _row(jid, j)
        for k in [k for k, r in rows.items() if not _keep(r, now)]:
            rows.pop(k, None)
        try:
            _store_save(rows)
        except Exception as e:  # noqa: BLE001 - a job isn't stopped by a list that couldn't be written
            log.warning("jobs: couldn't keep %s: %s", jid, e)


def finished(jid):
    """A job is done (whichever way): its end stamped, and its row kept when it's named."""
    j = _jobs.get(jid)
    if j is not None:
        j.setdefault("ended", time.time())
        _store(jid)


def name(jid, kind, one, many, ids=(), n=None):
    """A job's name in the Jobs list: `one` for a single book ({} its title, put in when the list is
    read), else `many` ({} how many). A job without one isn't listed (Edit book's steps, a book's own
    Find details and covers: parts of a sheet, as in Calibre)."""
    j = _jobs.get(jid) if jid else None
    if j is not None:
        ids = [int(i) for i in ids]
        n = len(ids) if n is None else n
        j.setdefault("kind", kind)
        j["name"] = {"one": one, "many": many, "id": ids[0] if n == 1 and ids else None, "n": n}
        _store(jid)
    return jid


def stop(jid):
    """Asks a start_each job to stop after the book it's on. False when it can't be stopped (not
    that kind of job, or already done)."""
    j = _jobs.get(jid)
    if not j or not j.get("stoppable") or not _running(j):
        return False
    j["stop"] = True
    return True


def jobs_list(titles=lambda ids: {}):
    """The named jobs, running first (newest first), then the last 30 finished, newest first:
    [{id, label, kind, state (running, done, failed, stopped, interrupted), started, ended, done,
    total, failed, errors [{id, title, error}], error, stoppable, stopping}]. titles({ids}) → {id: title}.
    Jobs from before a restart come from the kept rows; one still running then is interrupted."""
    _prune()
    now, rows = time.time(), []
    for jid, j in list(_jobs.items()):
        if not j.get("name"):
            continue
        run_ = _running(j)
        if not run_ and not j.get("ended"):
            j["ended"] = now                        # a job that doesn't stamp its own end: about now
        rows.append(dict(_row(jid, j), stoppable=bool(j.get("stoppable")) and run_ and not j.get("stop"), stopping=bool(j.get("stop")) and run_))
    for jid, r in list(stored().items()):
        if jid in _jobs or not _keep(r, now) or not isinstance(r.get("name"), dict):
            continue
        r = dict(r, stoppable=False, stopping=False, errors=[dict(e) for e in r.get("errors") or []])
        if r["state"] == "running":                 # running when Daf stopped
            r["state"] = "interrupted"
        rows.append(r)
    want = {r["name"]["id"] for r in rows if r["name"]["id"] is not None} | {e["id"] for r in rows for e in r["errors"] if e["id"] is not None}
    try:
        t = titles(want) if want else {}
    except Exception:  # noqa: BLE001 - a list without titles is still the list
        t = {}
    for r in rows:
        nm = r.pop("name")
        r["label"] = nm["one"].format("“%s”" % t[nm["id"]] if nm["id"] in t else "a book") if nm["n"] == 1 else nm["many"].format(nm["n"])
        for e in r["errors"]:
            e["title"] = t.get(e["id"])
    running = sorted((r for r in rows if r["state"] == "running"), key=lambda r: -r["started"])
    finished = sorted((r for r in rows if r["state"] != "running"), key=lambda r: -(r["ended"] or r["started"]))[:30]
    return running + finished
