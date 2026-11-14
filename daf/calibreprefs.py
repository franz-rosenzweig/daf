"""Calibre's Preferences → Metadata download, for Daf's own Calibre (the settings folder Find details
runs with, /config/.daf-calibre in Calibre-Web Automated's container): which metadata sources are
on and their cover priority, the fields to download (msprefs ignore_fields), the main options and
the tag mapper's rules.

Read and written by Calibre itself (calibre-debug), through the same objects its dialog uses
(calibre/gui2/preferences/metadata_sources.py): msprefs (metadata_sources/global.json) and
calibre.customize.ui's enable_plugin / disable_plugin / is_disabled (customize.py.json). So
calibrefind's IDENTIFY and COVERS scripts use them as they are: identify() takes the sources Calibre
has on, the wait times, max tags, swapped names, plain-text comments, fewer tags, keeping more than one
entry and the tag rules; the cover runs take the priorities and their wait. Nothing in the library is
touched, so it runs outside calibrewrite's lock.
"""
import json
import re
import subprocess
import threading

from . import calibrewrite as W

# The dialog's options (ConfigWidget.genesis registers these), with the ranges its spin boxes have.
BOOLS = ("txt_comments", "swap_author_names", "append_comments", "keep_dups", "fewer_tags")
INTS = {"max_tags": (0, 99), "wait_after_first_identify_result": (0, 99), "wait_after_first_cover_result": (0, 99)}
# Calibre's names for the fields (FieldsModel.descs); another field shows as its own name.
FIELD_LABELS = {"authors": "Authors", "comments": "Comments", "pubdate": "Published date", "publisher": "Publisher",
                "rating": "Rating", "tags": "Tags", "title": "Title", "series": "Series", "languages": "Languages"}
# The tag mapper (calibre/gui2/tag_mapper.py RuleEdit), its words.
ACTIONS = [("remove", "Remove"), ("replace", "Replace"), ("keep", "Keep"), ("capitalize", "Capitalize"),
           ("titlecase", "Title-case"), ("lower", "Lower-case"), ("upper", "Upper-case"), ("split", "Split")]
MATCHES = [("one_of", "is one of"), ("not_one_of", "is not one of"), ("matches", "matches pattern"),
           ("not_matches", "does not match pattern"), ("has", "contains")]
MAX_RULES, RULE_LEN = 100, 1000
PRIORITY = (1, 99)
_FIELD = re.compile(r"#?[a-z][a-z0-9_]{0,39}")
_lock = threading.Lock()

# The dialog's state, as Calibre has it: every source (sorted as the dialog sorts them), the fields
# the sources can fill, msprefs' values and its defaults (for Restore defaults).
READ = r'''
def main():
    import json
    from calibre.ebooks.metadata.sources.update import patch_plugins
    from calibre.ebooks.metadata.sources.prefs import msprefs
    from calibre.customize.ui import all_metadata_plugins, default_disabled_plugins, is_disabled
    from calibre.utils.icu import primary_sort_key
    patch_plugins()
    keys = ["txt_comments", "swap_author_names", "append_comments", "keep_dups", "fewer_tags", "max_tags",
            "wait_after_first_identify_result", "wait_after_first_cover_result", "ignore_fields", "tag_map_rules"]
    ps = sorted(all_metadata_plugins(), key=lambda p: primary_sort_key(p.name))
    cp, dcp = msprefs["cover_priorities"], msprefs.defaults["cover_priorities"]
    fields = set()
    for p in ps:
        fields |= set(p.touched_fields)
    out = {"ok": True,
           "sources": [{"name": p.name, "enabled": not is_disabled(p), "priority": int(cp.get(p.name, 1)),
                        "configured": bool(p.is_configured()), "covers": "cover" in p.capabilities, "identify": "identify" in p.capabilities,
                        "default_enabled": p.name not in default_disabled_plugins, "default_priority": int(dcp.get(p.name, 1))} for p in ps],
           "fields": sorted(f for f in fields if not f.startswith("identifier:") and f not in ("series_index", "language")),
           "prefs": {k: msprefs[k] for k in keys}, "defaults": {k: msprefs.defaults[k] for k in keys}}
    print("DAFRESULT " + json.dumps(out, default=list))
main()
'''

# The sheet's changes, the way the dialog commits them: a source's on/off only when it changed
# (enable_plugin / disable_plugin), its cover priority into cover_priorities (1, the default, taken
# out), and msprefs' keys that changed. Tag rules with a pattern are checked with the tag mapper's own
# compile first, and nothing is written if one doesn't compile.
WRITE = r'''
def main():
    import json, sys
    from calibre.ebooks.metadata.sources.update import patch_plugins
    from calibre.ebooks.metadata.sources.prefs import msprefs
    from calibre.ebooks.metadata.tag_mapper import compile_pat
    from calibre.customize.ui import all_metadata_plugins, disable_plugin, enable_plugin, is_disabled
    patch_plugins()
    job = json.loads(sys.stdin.read())
    prefs, sources = job.get("prefs") or {}, job.get("sources") or {}
    for r in prefs.get("tag_map_rules") or []:
        if "matches" in r["match_type"]:
            try:
                compile_pat(r["query"])
            except Exception:
                print("DAFRESULT " + json.dumps({"ok": False, "error": "Tag rules: “%s” isn't a pattern" % r["query"][:80]}))
                return
    cp = dict(msprefs["cover_priorities"])
    for p in all_metadata_plugins():
        s = sources.get(p.name)
        if not s:
            continue
        if "enabled" in s and bool(s["enabled"]) == is_disabled(p):
            if s["enabled"]:
                enable_plugin(p)
            else:
                try:
                    disable_plugin(p)
                except ValueError:
                    pass
        if "priority" in s:
            if int(s["priority"]) == 1:
                cp.pop(p.name, None)
            else:
                cp[p.name] = int(s["priority"])
    if cp != msprefs["cover_priorities"]:
        msprefs["cover_priorities"] = cp
    for k, v in prefs.items():
        if json.dumps(msprefs[k], default=list, sort_keys=True) != json.dumps(v, sort_keys=True):
            msprefs[k] = v
    print("DAFRESULT {\"ok\": true}")
main()
'''


class PrefsError(RuntimeError):
    pass


def _run(script, job=None, timeout=90):
    try:
        r = subprocess.run(W.RUN + [W.DEBUG, "-c", script], input=json.dumps(job or {}), capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise PrefsError(f"Calibre didn't answer: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        raise PrefsError("Calibre didn't answer" + (": " + r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ""))
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        raise PrefsError(out.get("error") or "Calibre said no")
    return out


def labels():
    return {"fields": FIELD_LABELS, "actions": ACTIONS, "matches": MATCHES}


def read():
    """The sheet's state: {sources, fields, prefs, defaults} as Calibre has them, plus the labels."""
    out = _run(READ)
    out.pop("ok", None)
    out["labels"] = labels()
    return out


def _int(v, lo, hi):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return int(round(min(hi, max(lo, n)))) if n == n and abs(n) != float("inf") else None


def clean_rule(r):
    """One tag mapper rule, Calibre's shape: {action, match_type, query, replace}; None when it isn't one."""
    if not isinstance(r, dict):
        return None
    action, mt = r.get("action"), r.get("match_type")
    query, rep = r.get("query"), r.get("replace", "")
    if action not in dict(ACTIONS) or mt not in dict(MATCHES) or not isinstance(query, str) or not isinstance(rep, str):
        return None
    query, rep = query.replace("\x00", ""), rep.replace("\x00", "")
    if not query.strip() or len(query) > RULE_LEN or len(rep) > RULE_LEN or "\n" in query + rep:
        return None
    if action == "split" and not rep:
        return None
    return {"action": action, "match_type": mt, "query": query, "replace": rep if action in ("replace", "split") else ""}


def clean(body):
    """The sheet's changes, every key checked against the dialog's: {prefs: {…}, sources: {name:
    {enabled, priority}}}. Unknown keys and bad values are dropped; numbers are clamped."""
    body = body if isinstance(body, dict) else {}
    p = body.get("prefs") if isinstance(body.get("prefs"), dict) else {}
    prefs = {}
    for k in BOOLS:
        if isinstance(p.get(k), bool):
            prefs[k] = p[k]
    for k, (lo, hi) in INTS.items():
        n = _int(p.get(k), lo, hi) if k in p else None
        if n is not None:
            prefs[k] = n
    if isinstance(p.get("ignore_fields"), list):
        prefs["ignore_fields"] = sorted({f for f in p["ignore_fields"] if isinstance(f, str) and _FIELD.fullmatch(f)})[:50]
    if isinstance(p.get("tag_map_rules"), list):
        prefs["tag_map_rules"] = [r for r in (clean_rule(x) for x in p["tag_map_rules"][:MAX_RULES]) if r]
    sources = {}
    s = body.get("sources") if isinstance(body.get("sources"), dict) else {}
    for name, v in list(s.items())[:100]:
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or not isinstance(v, dict):
            continue
        one = {}
        if isinstance(v.get("enabled"), bool):
            one["enabled"] = v["enabled"]
        n = _int(v.get("priority"), *PRIORITY) if "priority" in v else None
        if n is not None:
            one["priority"] = n
        if one:
            sources[name] = one
    return {"prefs": prefs, "sources": sources}


def write(body):
    """Cleans the sheet's changes and has Calibre write them; returns the new state."""
    job = clean(body)
    with _lock:
        _run(WRITE, job)
    return read()
