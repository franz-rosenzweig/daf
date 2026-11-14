"""Columns built from other columns (Calibre's composite columns): their values aren't stored, Calibre
works them out from each column's template. So Daf asks Calibre for them, on a copy of metadata.db
made with SQLite's backup (Calibre never opens the real one for this), whenever the library has
changed; the table uses the last values meanwhile, and waits only the very first time."""
import json
import logging
import subprocess
import threading

from . import calibrewrite as W

log = logging.getLogger("daf.composite")

SCRIPT = r'''
def main():
    import json, os, shutil, sqlite3, sys, tempfile
    job = json.loads(sys.stdin.read())
    tmp = tempfile.mkdtemp(prefix="daf-composite-")
    try:
        src = sqlite3.connect("file:" + os.path.join(job["lib"], "metadata.db") + "?mode=ro", uri=True)
        dst = sqlite3.connect(os.path.join(tmp, "metadata.db"))
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.close()
        src.close()
        from calibre.library import db as _db
        d = _db(tmp).new_api
        ids = list(d.all_book_ids())
        out = {}
        for label in job["labels"]:
            key = "#" + label
            if key not in d.field_metadata.keys():
                continue
            vals = d.all_field_for(key, ids, default_value="")
            out[key] = {str(i): (list(v) if isinstance(v, (list, tuple)) else ("" if v is None else str(v))) for i, v in vals.items()}
        print("DAFRESULT " + json.dumps({"ok": True, "values": out}))
    except Exception as e:
        print("DAFRESULT " + json.dumps({"ok": False, "error": str(e)}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
main()
'''

_state = {"key": None, "values": {}, "busy": False}
_lock = threading.Lock()


def columns(c):
    """The composite columns in a read-only connection to metadata.db: [{id, key, label, template, multi}]."""
    out = []
    for cid, label, name, multi, display in c.execute(
            "SELECT id, label, name, is_multiple, display FROM custom_columns WHERE datatype = 'composite' AND mark_for_delete = 0 ORDER BY id"):
        try:
            disp = json.loads(display or "{}") or {}
        except ValueError:
            disp = {}
        out.append({"id": cid, "key": "#" + label, "label": name or "#" + label, "template": disp.get("composite_template") or "", "multi": bool(multi)})
    return out


def _compute(key, cols):
    try:
        r = subprocess.run(W.RUN + [W.DEBUG, "-c", SCRIPT], input=json.dumps({"lib": W.LIB, "labels": [c["key"][1:] for c in cols]}),
                           capture_output=True, text=True, timeout=180)
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
        res = json.loads(line[len("DAFRESULT "):]) if line else {"ok": False, "error": (r.stderr or "")[-300:]}
        if res.get("ok"):
            vals = {k: {int(i): v for i, v in m.items()} for k, m in res["values"].items()}
            with _lock:
                _state.update(key=key, values=vals)
        else:
            log.warning("composite columns: %s", res.get("error"))
    except Exception as e:  # noqa: BLE001 - the last values stay
        log.warning("composite columns: %s", e)
    finally:
        with _lock:
            _state["busy"] = False


def values(key, cols):
    """{column key: {calibre id: value}} for the composite columns: the ones for this state of the
    library when known; else the last ones, while Calibre works out the new ones (waited for only when
    there are none yet)."""
    if not cols:
        return {}
    with _lock:
        fresh = _state["key"] == key and all(c["key"] in _state["values"] for c in cols)
        start = not fresh and not _state["busy"]
        first = not _state["values"]
        if start:
            _state["busy"] = True
    if start:
        if first:
            _compute(key, cols)
        else:
            threading.Thread(target=_compute, args=(key, cols), daemon=True).start()
    return _state["values"]


def cell(v, multi):
    """A composite value as the table keeps it: a list for a column that behaves like tags."""
    if multi:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return [x.strip() for x in str(v or "").split(",") if x.strip()]
    return v if v not in ("", None) else None
