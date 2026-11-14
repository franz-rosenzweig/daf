"""Edit book's Check spelling and Reports, with Calibre's own code (its Tools menu in Edit book).

Both read the working copy that ebookedit.py keeps (EDIT_DIR/<calibre id>/book) with calibre-debug in
Calibre-Web Automated's container, the way ebookedit's own tools do, and change nothing, except:

    Change all        a word replaced everywhere it's used (calibre.ebooks.oeb.polish.spell.replace_word),
                      with a checkpoint first, like the other tools
    Add to dictionary the word goes into Calibre's own user dictionary ("Default", in Daf's Calibre
                      settings: /config/.daf-calibre/dictionaries/prefs.json in the container)

Spelling is calibre.spell's: the book's language (the OPF's), xml:lang and lang inside the files,
Calibre's dictionaries (the ones that come with it, en-US, en-GB and es-ES, and any added to Daf's
Calibre settings), its user dictionaries, and Hunspell's suggestions. A language without a dictionary
counts every word as spelled right, as in Calibre. Ignore is the page's own, for while the book is open.

Reports are calibre.ebooks.oeb.polish.report's gather_data: files, words, images, links, characters
and style rules, each with where it is, so the page can open that file at that line.
"""
import json
import logging
import subprocess

from . import ebookedit as E

log = logging.getLogger("daf.ebooktools")
MAX_LOCS = 500          # a misspelled word's places sent to the page (its count is always all of them)
MAX_LOCS_OK = 20        # a correctly spelled word's
MAX_WORDS_REPORT = 1000

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

    def container():
        from calibre.ebooks.oeb.polish.container import get_container
        return get_container(book, log=quiet, tweak_mode=True, tdir=tempfile.mkdtemp(dir=tmp))

    def dictionaries(c):
        # Edit book's own: the book's language as the default (set_book_locale), else Calibre's
        from calibre.spell import parse_lang_code
        from calibre.spell.dictionary import Dictionaries
        d = Dictionaries()
        d.initialize()
        try:
            loc = parse_lang_code(c.mi.language)
            if loc.langcode == "und":
                raise ValueError("")
            d.default_locale = loc
        except Exception:
            pass
        return d

    def lkey(loc):
        return loc.langcode + ("-" + loc.countrycode if loc.countrycode else "")

    def locale_of(key):
        from calibre.spell import parse_lang_code
        return parse_lang_code(key)

    try:
        op = job["op"]
        if op == "spell":
            from calibre.ebooks.oeb.polish.spell import get_all_words
            from calibre.utils.localization import calibre_langcode_to_name
            c = container()
            d = dictionaries(c)
            words = get_all_words(c, d.default_locale)
            files, fidx, langs, rows = [], {}, {}, []
            for (w, loc), locs in words.items():
                k = lkey(loc)
                if k not in langs:
                    langs[k] = {"code": k, "name": calibre_langcode_to_name(loc.langcode), "dictionary": d.dictionary_for_locale(loc) is not None, "words": 0}
                langs[k]["words"] += len(locs)
                ok = bool(d.recognized(w, loc))
                flat = []
                for l in locs[:job["max_locs"] if not ok else job["max_locs_ok"]]:
                    if l.file_name not in fidx:
                        fidx[l.file_name] = len(files)
                        files.append(l.file_name)
                    flat += [fidx[l.file_name], l.sourceline or 0]
                rows.append([w, k, len(locs), ok, bool(d.word_in_user_dictionary(w, loc)), flat])
            rows.sort(key=lambda r: (r[3], -r[2], r[0].lower()))
            out.update(words=rows, files=files, langs=sorted(langs.values(), key=lambda x: -x["words"]),
                       default=lkey(d.default_locale))
        elif op == "suggest":
            from calibre.spell.dictionary import Dictionaries
            d = Dictionaries()
            d.initialize()
            loc = locale_of(job["lang"])
            out["suggestions"] = list(d.suggestions(job["word"], loc))[:15]
            out["dictionary"] = d.dictionary_for_locale(loc) is not None
        elif op == "add_word":
            from calibre.spell.dictionary import Dictionaries
            d = Dictionaries()
            d.initialize()
            name = d.active_user_dictionaries[0].name if d.active_user_dictionaries else "Default"
            out["added"] = bool(d.add_to_user_dictionary(name, job["word"], locale_of(job["lang"])))
            out["dictionary"] = name
        elif op == "change":
            from calibre.ebooks.oeb.polish.spell import get_all_words, replace_word
            c = container()
            d = dictionaries(c)
            words = get_all_words(c, d.default_locale)
            hit = [(w, loc) for (w, loc) in words if w == job["word"] and lkey(loc) == job["lang"]]
            changed = set()
            for w, loc in hit:
                changed |= replace_word(c, job["to"], words[(w, loc)], loc)
            if changed:
                c.commit()
            out["changed"] = sorted(changed)
            out["recognized"] = bool(d.recognized(job["to"], hit[0][1])) if hit else None
        elif op == "reports":
            from calibre.ebooks.oeb.polish.report import gather_data
            from calibre.utils.localization import calibre_langcode_to_name
            from calibre.utils.unicode_names import character_name_from_code
            c = container()
            d = dictionaries(c)
            data, _t = gather_data(c, d.default_locale)
            spine = {n: i for i, (n, _l) in enumerate(c.spine_names)}
            out["files"] = sorted(({"name": f.name, "size": f.size, "category": f.category, "words": f.word_count} for f in data["files"]),
                                  key=lambda f: (spine.get(f["name"], len(spine)), f["name"].lower()))
            count, wl = data["words"]
            ws = sorted(wl, key=lambda w: (-len(w.usage), w.word.lower()))
            per_lang = {}
            for w in wl:
                k = lkey(w.locale)
                per_lang[k] = per_lang.get(k, 0) + len(w.usage)
            out["words"] = {"total": count, "unique": len(wl),
                            "langs": [{"code": k, "name": calibre_langcode_to_name(k.split("-")[0]), "words": n} for k, n in sorted(per_lang.items(), key=lambda x: -x[1])],
                            "list": [[w.word, lkey(w.locale), len(w.usage), w.usage[0].file_name if w.usage else None, w.usage[0].sourceline if w.usage else None] for w in ws[:job["max_words"]]]}
            out["images"] = [{"name": i.name, "type": i.mime_type, "size": i.size, "width": i.width, "height": i.height,
                              "used": [[u.name, u.line_number] for u in i.usage]} for i in data["images"]]
            links = []
            for l in data["links"]:
                links.append({"name": l.location.name, "line": l.location.line_number, "text": l.text or "", "href": l.href or "",
                              "external": bool(l.is_external), "ok": l.ok, "anchor": l.anchor.id if l.anchor else None,
                              "dest": l.anchor.location.name if l.anchor and l.anchor.location else None,
                              "dest_line": l.anchor.location.line_number if l.anchor and l.anchor.location else None})
            out["links"] = links
            names = {0xa: "LINE FEED", 0xd: "CARRIAGE RETURN", 0x9: "TAB"}
            out["chars"] = sorted(({"char": ch.char, "code": ch.codepoint, "name": names.get(ch.codepoint) or character_name_from_code(ch.codepoint) or "",
                                    "count": ch.count, "files": list(ch.usage)} for ch in data["chars"]), key=lambda x: -x["count"])
            css = []
            for e in data["css"]:
                css.append({"selector": e.rule.selector, "name": e.rule.location.file_name, "line": e.rule.location.line, "count": e.count,
                            "matched": [[m.file_name, [l.sourceline for l in m.locations][:50]] for m in e.matched_files]})
            out["css"] = sorted(css, key=lambda x: (x["count"] > 0, x["name"], x["line"]))
        else:
            raise ValueError("unknown op " + op)
    except Exception as e:
        msg = str(e) or e.__class__.__name__
        out = {"ok": False, "error": msg, "trace": traceback.format_exc()[-1500:]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("DAFRESULT " + json.dumps(out))
main()
'''


def _run(cid, job, timeout=900):
    """One of these jobs for Calibre, on this book's working copy; its answer, or EditError."""
    from . import calibrewrite as W
    job = dict(job, dir=E.inside(E.home(cid)))
    try:
        r = subprocess.run(W.RUN + [W.DEBUG, "-c", SCRIPT], input=json.dumps(job), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise E.EditError("Calibre took too long")
    except OSError as e:
        raise E.EditError(f"Couldn't reach Calibre: {e}")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("DAFRESULT ")), None)
    if not line:
        log.warning("calibre-debug said: %s %s", r.stdout[-800:], r.stderr[-800:])
        raise E.EditError("Calibre didn't answer")
    out = json.loads(line[len("DAFRESULT "):])
    if not out.get("ok"):
        log.warning("edit book %s failed: %s", job.get("op"), out.get("trace"))
        raise E.EditError(out.get("error") or "Calibre said no")
    out.pop("ok", None)
    return out


def _word(w):
    w = str(w or "").strip()
    if not w or len(w) > 200 or any(ch in w for ch in "<>&\n\r\t"):
        raise E.EditError("A word")
    return w


def _lang(lang):
    lang = str(lang or "").strip()
    if not lang or len(lang) > 20 or not all(ch.isalnum() or ch == "-" for ch in lang):
        raise E.EditError("A language")
    return lang


def spell(cid):
    """Every word in the book, as Calibre's Check spelling has them: {words: [[word, lang, count,
    spelled right, in the user dictionary, [file index, line, …]]] misspelled first, then the most
    used; files: [names]; langs: [{code, name, dictionary, words}]; default: the book's language}."""
    E._need(cid)
    with E._lock(cid):
        return _run(cid, {"op": "spell", "max_locs": MAX_LOCS, "max_locs_ok": MAX_LOCS_OK})


def suggest(cid, word, lang):
    """Hunspell's suggestions for a word, from the dictionary for its language: {suggestions, dictionary}."""
    E._need(cid)
    return _run(cid, {"op": "suggest", "word": _word(word), "lang": _lang(lang)}, timeout=120)


def add_word(cid, word, lang):
    """Into Calibre's user dictionary (the first one that's on, "Default" unless it was renamed)."""
    E._need(cid)
    return _run(cid, {"op": "add_word", "word": _word(word), "lang": _lang(lang)}, timeout=120)


def change_all(cid, word, to, lang):
    """Every use of a word (in that language) replaced, as Calibre's Change all does; a checkpoint
    first, dropped again when nothing changed."""
    E._need(cid)
    word, to, lang = _word(word), _word(to), _lang(lang)
    with E._lock(cid):
        n = E.checkpoint(cid, "Change all")
        try:
            out = _run(cid, {"op": "change", "word": word, "to": to, "lang": lang})
        except Exception:
            E._drop_checkpoint(cid, n)
            raise
        if out.get("changed"):
            E._changed(cid)
            out["checkpoint"] = n
        else:
            E._drop_checkpoint(cid, n)
    return out


def reports(cid):
    """Calibre's Reports for the working copy: {files, words, images, links, chars, css}."""
    E._need(cid)
    with E._lock(cid):
        return _run(cid, {"op": "reports", "max_words": MAX_WORDS_REPORT})
