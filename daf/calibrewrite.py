"""Changes to the Calibre library, made by Calibre itself. Daf never writes metadata.db: each change
is a short script run with calibre-debug inside Calibre-Web Automated's container (DAF_CALIBRE_RUN),
using Calibre's own library API. So Calibre's rules hold: a new title or author moves the book's
folder, the sort fields follow, a removed book goes to Calibre's trash, a cover is resized the way
Calibre does it, and metadata.opf beside each book is written again.

One change at a time (a lock): Calibre-Web Automated's imports go through Calibre too, and SQLite
waits for whichever is first.

    DAF_CALIBRE_RUN   how to reach Calibre (default: docker exec -i -u abc calibre-web-automated)
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
RUN = shlex.split(os.environ.get("DAF_CALIBRE_RUN", "docker exec -i -u abc calibre-web-automated"))
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
    job = json.loads(sys.stdin.read())
    d = _db(job["lib"]).new_api
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
            if missing:
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
            elif k == "convert":
                src = d.format_abspath(ids[0], op["from"].upper())
                if not src:
                    raise ValueError("The book has no %s file" % op["from"].upper())
                tmp = tempfile.mkdtemp()
                dst = os.path.join(tmp, "book." + op["to"].lower())
                r = subprocess.run(["/app/calibre/ebook-convert", src, dst], capture_output=True, text=True, timeout=900)
                if r.returncode or not os.path.exists(dst):
                    raise ValueError("Calibre couldn't convert it: " + (r.stderr or r.stdout or "")[-400:])
                d.add_format(ids[0], op["to"].upper(), dst, replace=True)
                os.unlink(dst); os.rmdir(tmp)
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
            elif k == "remove_books":
                d.remove_books(ids)
                for i in ids:
                    out["books"][str(i)] = None
                out["done"].append(k)
                continue
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
    if "trash" in out:
        books["trash"] = out["trash"]
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


# ---------- conversions take a while: a job the page asks about ----------
_jobs = {}


def start_convert(cid, src, to):
    jid = uuid.uuid4().hex[:12]
    _jobs[jid] = {"state": "running", "started": time.time(), "id": cid, "to": to.upper()}

    def work():
        try:
            run([{"op": "convert", "id": cid, "from": src, "to": to}], timeout=1000)
            _jobs[jid].update(state="done")
        except Exception as e:  # noqa: BLE001 - the page says what went wrong
            _jobs[jid].update(state="failed", error=str(e))
    threading.Thread(target=work, daemon=True).start()
    for k in [k for k, j in _jobs.items() if time.time() - j["started"] > 86400]:
        _jobs.pop(k, None)
    return jid


def job(jid):
    return _jobs.get(jid)
