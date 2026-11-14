"""Calibre's Preferences → Metadata download, for Daf's own Calibre (the settings folder Find details
runs with, /config/.daf-calibre in Calibre-Web Automated's container): which metadata sources are
on and their cover priority, each source's own settings (Calibre's Configure selected source), the
fields to download (msprefs ignore_fields), the main options and the rules that transform downloaded
tags, authors, publishers and series.

Read and written by Calibre itself (calibre-debug), through the same objects its dialogs use
(calibre/gui2/preferences/metadata_sources.py, calibre/gui2/metadata/config.py): msprefs
(metadata_sources/global.json), calibre.customize.ui's enable_plugin / disable_plugin / is_disabled
(customize.py.json), each source's prefs (metadata_sources/<source>.json: its Option list and its own
ignore_fields) and, for the Goodreads and Goodreads More Tags plugins, the prefs their own config
dialogs keep (plugins/Goodreads.json, plugins/goodreads-more-tags.json). So calibrefind's IDENTIFY
and COVERS scripts use them as they are. Nothing in the library is touched, so it runs outside
calibrewrite's lock.
"""
import json
import math
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
# The mappers' rule dialogs (calibre/gui2/tag_mapper.py, author_mapper.py, publisher_mapper.py,
# series_mapper.py), their words. "replace" says which actions take the replacement.
ACTIONS = [("remove", "Remove"), ("replace", "Replace"), ("keep", "Keep"), ("capitalize", "Capitalize"),
           ("titlecase", "Title-case"), ("lower", "Lower-case"), ("upper", "Upper-case"), ("split", "Split")]
MATCHES = [("one_of", "is one of"), ("not_one_of", "is not one of"), ("matches", "matches pattern"),
           ("not_matches", "does not match pattern"), ("has", "contains")]
_NAME_ACTIONS = [("replace", "Change"), ("capitalize", "Capitalize"), ("titlecase", "Title-case"), ("lower", "Lower-case"), ("upper", "Upper-case")]
_REGEX_MATCHES = [("has", "contains"), ("matches", "matches regex pattern"), ("not_matches", "does not match regex pattern")]
RULES = {
    "tag_map_rules": {"title": "Tag rules", "actions": ACTIONS, "matches": MATCHES, "replace": ("replace", "split"), "with": "with the tag", "split": "on the character"},
    "author_map_rules": {"title": "Author rules", "actions": [a for a in _NAME_ACTIONS if a[0] != "titlecase"],
                         "matches": [("one_of", "is one of"), ("not_one_of", "is not one of")] + _REGEX_MATCHES, "replace": ("replace",), "with": "with the name"},
    "publisher_map_rules": {"title": "Publisher rules", "actions": _NAME_ACTIONS,
                            "matches": [("one_of", "is"), ("not_one_of", "is not")] + _REGEX_MATCHES, "replace": ("replace",), "with": "with the name"},
    "series_map_rules": {"title": "Series rules", "actions": _NAME_ACTIONS,
                         "matches": [("one_of", "is"), ("not_one_of", "is not")] + _REGEX_MATCHES, "replace": ("replace",), "with": "with the name"},
}
MAX_RULES, RULE_LEN = 100, 1000
PRIORITY = (1, 99)
# The two plugins with config dialogs of their own: the options those dialogs have, in their words.
GOODREADS = [("mapGenres", "Filter and map genres to calibre tags"),
             ("getAllAuthors", "Get all contributing authors (e.g. illustrators, series editors etc)"),
             ("getAsin", "Get ASIN for kindle editions"), ("firstPublished", "Use first published date"),
             ("getRating", "Get precise rating into 'grrating' identifier"), ("getVotes", "Get #votes for rating into 'grvotes' identifier")]
GOODREADS_MORE_TAGS = [{"key": "absolute", "type": "int", "label": "Threshold (absolute)", "min": 0, "max": 1000000},
                       {"key": "percentage", "type": "float", "label": "Threshold (percentage)", "min": 0, "max": 100, "unit": "%"},
                       {"key": "percentageOf", "type": "ints", "label": "Threshold percentage is based on"},
                       {"key": "enabled", "type": "bool", "label": "Goodreads Plugin Integration"},
                       {"key": "timeout", "type": "float", "label": "Timeout", "min": 0.1, "max": 600, "unit": "secs"}]
MAX_MAPPINGS, MAP_LEN, MAP_TAGS = 1000, 100, 20
_FIELD = re.compile(r"#?[a-z][a-z0-9_]{0,39}")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,59}")
_lock = threading.Lock()

# The dialog's state, as Calibre has it: every source (sorted as the dialog sorts them) with its own
# settings, the fields the sources can fill, msprefs' values and its defaults (for Restore defaults).
READ = r'''
def main():
    import json
    from calibre.ebooks.metadata.sources.update import patch_plugins
    from calibre.ebooks.metadata.sources.prefs import msprefs
    from calibre.customize.ui import all_metadata_plugins, default_disabled_plugins, is_disabled
    from calibre.utils.icu import primary_sort_key, sort_key
    patch_plugins()
    keys = ["txt_comments", "swap_author_names", "append_comments", "keep_dups", "fewer_tags", "max_tags",
            "wait_after_first_identify_result", "wait_after_first_cover_result", "ignore_fields",
            "tag_map_rules", "author_map_rules", "publisher_map_rules", "series_map_rules"]

    def nget(cfg, path):                          # a nested setting as stored, else the plugin's default, never writing
        root = dict(cfg)
        for k in path[:-1]:
            root = root.get(k) if isinstance(root, dict) else None
        if isinstance(root, dict) and path[-1] in root:
            return root[path[-1]]
        return cfg.get_default(path)

    def conf(p):                                  # Configure selected source: calibre/gui2/metadata/config.py and the plugins' own
        fields = sorted(f for f in p.touched_fields if not f.startswith("identifier:") and f not in ("title", "authors", "series_index", "language"))
        opts = []
        for o in p.options:
            ch = sorted(([k, str(v)] for k, v in o.choices.items()), key=lambda kv: sort_key(kv[1])) if o.type == "choices" and o.choices else None
            opts.append({"name": o.name, "type": o.type, "label": str(o.label), "value": p.prefs[o.name], "default": o.default,
                         "whole": isinstance(o.default, int) and not isinstance(o.default, bool), "choices": ch})
        extra, mod = None, type(p).__module__
        try:
            if mod == "calibre_plugins.goodreads":
                from calibre_plugins.goodreads.config import STORE_NAME, KEY_GENRE_MAPPINGS, get_plugin_prefs
                v = dict(get_plugin_prefs(STORE_NAME, fill_defaults=True))
                extra = {"kind": "goodreads", "values": {k: x for k, x in v.items() if k != KEY_GENRE_MAPPINGS}, "mappings": v.get(KEY_GENRE_MAPPINGS) or {}}
            elif mod == "calibre_plugins.goodreads_more_tags":
                from calibre_plugins.goodreads_more_tags import config as g
                pp = g.plugin_prefs
                extra = {"kind": "goodreads_more_tags", "values": {"absolute": nget(pp, g.KEY_THRESHOLD_ABSOLUTE), "percentage": nget(pp, g.KEY_THRESHOLD_PERCENTAGE),
                         "percentageOf": nget(pp, g.KEY_THRESHOLD_PERCENTAGE_OF), "enabled": nget(pp, g.KEY_INTEGRATION_ENABLED),
                         "timeout": nget(pp, g.KEY_INTEGRATION_TIMEOUT)}, "mappings": nget(pp, g.KEY_SHELF_MAPPINGS) or {}}
        except Exception as e:
            extra = {"kind": "error", "error": str(e)[:200]}
        return {"fields": fields, "ignore_fields": sorted(p.prefs["ignore_fields"]), "options": opts, "extra": extra}

    ps = sorted(all_metadata_plugins(), key=lambda p: primary_sort_key(p.name))
    cp, dcp = msprefs["cover_priorities"], msprefs.defaults["cover_priorities"]
    fields = set()
    for p in ps:
        fields |= set(p.touched_fields)
    out = {"ok": True,
           "sources": [{"name": p.name, "enabled": not is_disabled(p), "priority": int(cp.get(p.name, 1)),
                        "configured": bool(p.is_configured()), "covers": "cover" in p.capabilities, "identify": "identify" in p.capabilities,
                        "default_enabled": p.name not in default_disabled_plugins, "default_priority": int(dcp.get(p.name, 1)),
                        "config": conf(p)} for p in ps],
           "fields": sorted(f for f in fields if not f.startswith("identifier:") and f not in ("series_index", "language")),
           "prefs": {k: msprefs[k] for k in keys}, "defaults": {k: msprefs.defaults[k] for k in keys}}
    print("DAFRESULT " + json.dumps(out, default=list))
main()
'''

# The sheet's changes, the way the dialogs commit them: a source's on/off only when it changed
# (enable_plugin / disable_plugin), its cover priority into cover_priorities (1, the default, taken
# out), its own options checked against its Option list (the type, Calibre's spin-box range, a choice
# it offers) and its own fields to download, the two plugins' own settings, and msprefs' keys that
# changed. Every rule list is checked with Calibre's own compilers first (the tag mapper's for tags,
# publishers and series, the author mapper's for authors), and nothing is written if one fails.
WRITE = r'''
def main():
    import json, sys
    from calibre.ebooks.metadata.sources.update import patch_plugins
    from calibre.ebooks.metadata.sources.prefs import msprefs
    from calibre.ebooks.metadata.tag_mapper import matcher
    from calibre.ebooks.metadata.author_mapper import compile_rules
    from calibre.customize.ui import all_metadata_plugins, disable_plugin, enable_plugin, is_disabled
    patch_plugins()
    job = json.loads(sys.stdin.read())
    prefs, sources = job.get("prefs") or {}, job.get("sources") or {}
    names = {"tag_map_rules": ("Tag rules", ","), "publisher_map_rules": ("Publisher rules", ""), "series_map_rules": ("Series rules", "")}
    for key, rules in [(k, prefs[k]) for k in ("tag_map_rules", "author_map_rules", "publisher_map_rules", "series_map_rules") if k in prefs]:
        for r in rules:
            try:
                if key == "author_map_rules":
                    compile_rules([r])
                else:
                    matcher(r, names[key][1])
            except Exception:
                title = names[key][0] if key in names else "Author rules"
                print("DAFRESULT " + json.dumps({"ok": False, "error": "%s: “%s” isn't a pattern" % (title, r["query"][:80])}))
                return

    def option(o, v, cur):                        # a value the source's own dialog could have saved, or None
        if o.type == "bool":
            return v if isinstance(v, bool) else None
        if o.type == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None
            whole = isinstance(o.default, int) and not isinstance(o.default, bool)
            top = 99 if whole else 99.99
            lo, hi = min(0, 20 * (cur or 0)), max(top, 20 * (cur or 0))
            v = min(hi, max(lo, v))
            return int(round(v)) if whole else float(v)
        if o.type == "string":
            return v[:500] if isinstance(v, str) else None
        if o.type == "choices":
            return v if v in (o.choices or {}) else None
        return None

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
        for name, v in (s.get("options") or {}).items():
            o = next((o for o in p.options if o.name == name), None)
            if o is None:
                continue
            v = option(o, v, p.prefs[o.name])
            if v is not None or (o.type == "choices" and None in (o.choices or {}) and s["options"][name] is None):
                if p.prefs[o.name] != v:
                    p.prefs[o.name] = v
        if "ignore_fields" in s:                  # this source's own: the ones its page shows, the rest kept
            shown = {f for f in p.touched_fields if not f.startswith("identifier:") and f not in ("title", "authors", "series_index", "language")}
            new = sorted({f for f in p.prefs["ignore_fields"] if f not in shown} | (set(s["ignore_fields"]) & shown))
            if new != sorted(p.prefs["ignore_fields"]):
                p.prefs["ignore_fields"] = new
        mod = type(p).__module__
        g = s.get("goodreads")
        if g and mod == "calibre_plugins.goodreads":
            from calibre_plugins.goodreads.config import plugin_prefs, STORE_NAME, KEY_GENRE_MAPPINGS, get_plugin_prefs
            cur = dict(get_plugin_prefs(STORE_NAME, fill_defaults=True))
            new = dict(cur)
            for k, v in (g.get("values") or {}).items():
                if k in cur and k != KEY_GENRE_MAPPINGS and isinstance(v, bool):
                    new[k] = v
            if isinstance(g.get("mappings"), dict):
                new[KEY_GENRE_MAPPINGS] = g["mappings"]
            if new != cur:
                plugin_prefs[STORE_NAME] = new    # the whole store, as its dialog's commit writes it
        g = s.get("goodreads_more_tags")
        if g and mod == "calibre_plugins.goodreads_more_tags":
            from calibre_plugins.goodreads_more_tags import config as c
            keys = {"absolute": c.KEY_THRESHOLD_ABSOLUTE, "percentage": c.KEY_THRESHOLD_PERCENTAGE, "percentageOf": c.KEY_THRESHOLD_PERCENTAGE_OF,
                    "enabled": c.KEY_INTEGRATION_ENABLED, "timeout": c.KEY_INTEGRATION_TIMEOUT}
            changed = False
            for k, v in (g.get("values") or {}).items():
                if k in keys:
                    c.plugin_prefs.set(keys[k], v)
                    changed = True
            if isinstance(g.get("mappings"), dict):
                c.plugin_prefs.set(c.KEY_SHELF_MAPPINGS, g["mappings"])
                changed = True
            if changed:
                c.plugin_prefs.commit()
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
    return {"fields": FIELD_LABELS, "actions": ACTIONS, "matches": MATCHES,
            "rules": {k: {kk: v[kk] for kk in ("title", "actions", "matches", "replace", "with", "split") if kk in v} for k, v in RULES.items()},
            "goodreads": GOODREADS, "goodreads_more_tags": GOODREADS_MORE_TAGS,
            "mappings": {"goodreads": {"title": "Goodreads genre to calibre tag mappings", "cols": ["Goodreads Genre", "Maps to Calibre Tag"]},
                         "goodreads_more_tags": {"title": "", "cols": ["Goodreads Shelf", "Calibre Tag(s)"]}}}


def read():
    """The sheet's state: {sources (each with config), fields, prefs, defaults} as Calibre has them, plus the labels."""
    out = _run(READ)
    out.pop("ok", None)
    out["labels"] = labels()
    return out


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _int(v, lo, hi):
    n = _num(v)
    return None if n is None else int(round(min(hi, max(lo, n))))


def clean_rule(r, kind="tag_map_rules"):
    """One mapper rule, Calibre's shape: {action, match_type, query, replace}; None when it isn't one
    of this mapper's."""
    spec = RULES[kind]
    if not isinstance(r, dict):
        return None
    action, mt = r.get("action"), r.get("match_type")
    query, rep = r.get("query"), r.get("replace", "")
    if action not in dict(spec["actions"]) or mt not in dict(spec["matches"]) or not isinstance(query, str) or not isinstance(rep, str):
        return None
    query, rep = query.replace("\x00", ""), rep.replace("\x00", "")
    if not query.strip() or len(query) > RULE_LEN or len(rep) > RULE_LEN or "\n" in query + rep:
        return None
    if action == "split" and not rep:
        return None
    return {"action": action, "match_type": mt, "query": query, "replace": rep if action in spec["replace"] else ""}


def _text(v, n):
    return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= n and not re.search(r"[\x00-\x1f\x7f]", v)


def clean_mappings(m):
    """A plugin's name → tags table ({genre or shelf: [tags]}); None when it isn't one."""
    if not isinstance(m, dict):
        return None
    out = {}
    for k, tags in list(m.items())[:MAX_MAPPINGS]:
        if not _text(k, MAP_LEN) or not isinstance(tags, list):
            continue
        out[k.strip()] = list(dict.fromkeys(t.strip() for t in tags if _text(t, MAP_LEN) and "," not in t))[:MAP_TAGS]
    return out


def _clean_source(v):
    one = {}
    if isinstance(v.get("enabled"), bool):
        one["enabled"] = v["enabled"]
    n = _int(v.get("priority"), *PRIORITY) if "priority" in v else None
    if n is not None:
        one["priority"] = n
    if isinstance(v.get("ignore_fields"), list):
        one["ignore_fields"] = sorted({f for f in v["ignore_fields"] if isinstance(f, str) and _FIELD.fullmatch(f)})[:50]
    if isinstance(v.get("options"), dict):           # checked again in Calibre against the source's own Option list
        opts = {}
        for k, x in list(v["options"].items())[:50]:
            if isinstance(k, str) and _IDENT.fullmatch(k) and (x is None or isinstance(x, (bool, int, float)) and not (isinstance(x, float) and not math.isfinite(x))
                                                              or isinstance(x, str) and len(x) <= 500):
                opts[k] = x
        if opts:
            one["options"] = opts
    g = v.get("goodreads")
    if isinstance(g, dict):
        vals = {k: g["values"][k] for k, _l in GOODREADS if isinstance(g.get("values"), dict) and isinstance(g["values"].get(k), bool)}
        gr = {"values": vals} if vals else {}
        m = clean_mappings(g.get("mappings")) if "mappings" in g else None
        if m is not None:
            gr["mappings"] = m
        if gr:
            one["goodreads"] = gr
    g = v.get("goodreads_more_tags")
    if isinstance(g, dict):
        vals, raw = {}, g.get("values") if isinstance(g.get("values"), dict) else {}
        for c in GOODREADS_MORE_TAGS:
            x = raw.get(c["key"])
            if c["type"] == "bool" and isinstance(x, bool):
                vals[c["key"]] = x
            elif c["type"] in ("int", "float") and _num(x) is not None:
                n = min(c["max"], max(c["min"], _num(x)))
                vals[c["key"]] = int(round(n)) if c["type"] == "int" else round(n, 2)
            elif c["type"] == "ints" and isinstance(x, list) and x and all(_num(i) is not None and not isinstance(i, str) for i in x):
                vals[c["key"]] = [max(1, min(100, int(i))) for i in x][:20]
        gm = {"values": vals} if vals else {}
        m = clean_mappings(g.get("mappings")) if "mappings" in g else None
        if m is not None:
            gm["mappings"] = m
        if gm:
            one["goodreads_more_tags"] = gm
    return one


def clean(body):
    """The sheet's changes, every key checked against the dialogs': {prefs: {…}, sources: {name:
    {enabled, priority, ignore_fields, options, goodreads, goodreads_more_tags}}}. Unknown keys and bad
    values are dropped; numbers are clamped."""
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
    for kind in RULES:
        if isinstance(p.get(kind), list):
            prefs[kind] = [r for r in (clean_rule(x, kind) for x in p[kind][:MAX_RULES]) if r]
    sources = {}
    s = body.get("sources") if isinstance(body.get("sources"), dict) else {}
    for name, v in list(s.items())[:100]:
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or not isinstance(v, dict):
            continue
        one = _clean_source(v)
        if one:
            sources[name] = one
    return {"prefs": prefs, "sources": sources}


def write(body):
    """Cleans the sheet's changes and has Calibre write them; returns the new state."""
    job = clean(body)
    with _lock:
        _run(WRITE, job)
    return read()
