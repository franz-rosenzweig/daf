"""Calibre's Preferences → Metadata download for Daf's Calibre (calibreprefs.py): what the sheet may
change and how it's checked, what goes to Calibre's own prefs objects, and Find details carrying the
chosen fields back with its answers."""
import json
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import calibrefind, calibreprefs as cp  # noqa: E402

STATE = {"ok": True, "sources": [{"name": "Google", "enabled": True, "priority": 2, "configured": True, "covers": True, "identify": True,
                                  "default_enabled": True, "default_priority": 2}],
         "fields": ["authors", "tags", "title"], "prefs": {"max_tags": 20, "ignore_fields": []}, "defaults": {"max_tags": 20, "ignore_fields": []}}


class Clean(unittest.TestCase):
    def test_unknown_keys_dropped(self):
        out = cp.clean({"prefs": {"cover_priorities": {"Google": 9}, "id_link_rules": {"x": "y"}, "user_default_ignore_fields": [], "author_map_rule": [],
                                  "find_first_edition_date": True, "max_tags": 5}, "plugins": {"x": 1}, "sources": {}})
        self.assertEqual(out, {"prefs": {"max_tags": 5}, "sources": {}})

    def test_options(self):
        out = cp.clean({"prefs": {"txt_comments": True, "swap_author_names": "yes", "append_comments": 1, "keep_dups": False, "fewer_tags": None,
                                  "max_tags": 500, "wait_after_first_identify_result": -4, "wait_after_first_cover_result": "45"}})["prefs"]
        self.assertEqual(out, {"txt_comments": True, "keep_dups": False, "max_tags": 99, "wait_after_first_identify_result": 0, "wait_after_first_cover_result": 45})
        for bad in (True, "ten", float("nan"), float("inf"), None, [3]):
            self.assertEqual(cp.clean({"prefs": {"max_tags": bad}})["prefs"], {}, bad)

    def test_fields(self):
        out = cp.clean({"prefs": {"ignore_fields": ["title", "pubdate", "title", "identifier:isbn", "Authors", "", 7, "#pages", "a" * 60]}})["prefs"]
        self.assertEqual(out["ignore_fields"], ["#pages", "pubdate", "title"])
        self.assertEqual(cp.clean({"prefs": {"ignore_fields": []}})["prefs"], {"ignore_fields": []})
        self.assertNotIn("ignore_fields", cp.clean({"prefs": {"ignore_fields": "title"}})["prefs"])

    def test_tag_rules(self):
        rules = [{"action": "remove", "match_type": "one_of", "query": "fiction, general", "replace": "ignored"},
                 {"action": "replace", "match_type": "matches", "query": "^sci-?fi$", "replace": "Science Fiction"},
                 {"action": "split", "match_type": "has", "query": "/", "replace": "/"},
                 {"action": "split", "match_type": "has", "query": "/", "replace": ""},           # split needs its character
                 {"action": "explode", "match_type": "one_of", "query": "x"},
                 {"action": "remove", "match_type": "sounds_like", "query": "x"},
                 {"action": "remove", "match_type": "one_of", "query": "  "},
                 {"action": "remove", "match_type": "one_of", "query": "a\nb"},
                 {"action": "remove", "match_type": "one_of", "query": "x" * 1001},
                 {"action": "remove", "match_type": "one_of", "query": 5},
                 "remove fiction"]
        out = cp.clean({"prefs": {"tag_map_rules": rules}})["prefs"]["tag_map_rules"]
        self.assertEqual(out, [{"action": "remove", "match_type": "one_of", "query": "fiction, general", "replace": ""},
                               {"action": "replace", "match_type": "matches", "query": "^sci-?fi$", "replace": "Science Fiction"},
                               {"action": "split", "match_type": "has", "query": "/", "replace": "/"}])
        many = [{"action": "lower", "match_type": "has", "query": "q%d" % i} for i in range(300)]
        self.assertEqual(len(cp.clean({"prefs": {"tag_map_rules": many}})["prefs"]["tag_map_rules"]), cp.MAX_RULES)

    def test_sources(self):
        out = cp.clean({"sources": {"Google": {"enabled": False, "priority": 0}, "Amazon.com": {"priority": "300"}, "Goodreads": {"enabled": "no"},
                                    "": {"enabled": True}, "x" * 101: {"enabled": True}, "Open Library": "on", "Edelweiss": {"enabled": True, "other": 1}}})["sources"]
        self.assertEqual(out, {"Google": {"enabled": False, "priority": 1}, "Amazon.com": {"priority": 99}, "Edelweiss": {"enabled": True}})

    def test_not_objects(self):
        self.assertEqual(cp.clean(None), {"prefs": {}, "sources": {}})
        self.assertEqual(cp.clean({"prefs": [1], "sources": [2]}), {"prefs": {}, "sources": {}})


class Mappers(unittest.TestCase):
    def test_each_mapper_has_its_own_actions(self):
        ok = {"action": "replace", "match_type": "one_of", "query": "a & b", "replace": "A"}
        for kind in cp.RULES:
            self.assertEqual(cp.clean_rule(ok, kind), ok)
        self.assertIsNone(cp.clean_rule({"action": "remove", "match_type": "one_of", "query": "x"}, "author_map_rules"))     # tags only
        self.assertIsNone(cp.clean_rule({"action": "titlecase", "match_type": "has", "query": "x"}, "author_map_rules"))
        self.assertEqual(cp.clean_rule({"action": "titlecase", "match_type": "has", "query": "x", "replace": "y"}, "series_map_rules"),
                         {"action": "titlecase", "match_type": "has", "query": "x", "replace": ""})
        self.assertIsNone(cp.clean_rule({"action": "split", "match_type": "has", "query": "x", "replace": "/"}, "publisher_map_rules"))

    def test_clean_takes_all_four(self):
        body = {"prefs": {k: [{"action": "upper", "match_type": "has", "query": "q"}, {"action": "nope", "match_type": "has", "query": "q"}] for k in cp.RULES}}
        out = cp.clean(body)["prefs"]
        self.assertEqual(sorted(out), sorted(cp.RULES))
        self.assertTrue(all(out[k] == [{"action": "upper", "match_type": "has", "query": "q", "replace": ""}] for k in cp.RULES))

    def test_labels(self):
        L = cp.labels()
        self.assertEqual(L["rules"]["author_map_rules"]["actions"][0], ("replace", "Change"))
        self.assertEqual(dict(L["rules"]["publisher_map_rules"]["matches"])["one_of"], "is")
        self.assertEqual(L["rules"]["tag_map_rules"]["replace"], ("replace", "split"))
        json.dumps(L)


class Sources(unittest.TestCase):
    def src(self, v):
        return cp.clean({"sources": {"S": v}})["sources"].get("S")

    def test_options_and_fields(self):
        out = self.src({"options": {"domain": "uk", "max_covers": 3, "use_mobi_asin": True, "additional_country": None, "bad key": 1, "x" * 61: 1,
                                    "big": "x" * 501, "nan": float("nan"), "list": [1], "obj": {}},
                        "ignore_fields": ["comments", "identifier:isbn", "Title"]})
        self.assertEqual(out, {"options": {"domain": "uk", "max_covers": 3, "use_mobi_asin": True, "additional_country": None}, "ignore_fields": ["comments"]})
        self.assertIsNone(self.src({"options": {"bad key": 1}}))

    def test_goodreads(self):
        out = self.src({"goodreads": {"values": {"getAsin": True, "mapGenres": "yes", "other": True},
                                      "mappings": {"Science Fiction": ["Science Fiction", "SF", "a, b", ""], "": ["x"], "Bad\nKey": ["x"], "Ok": "not a list"}}})
        self.assertEqual(out, {"goodreads": {"values": {"getAsin": True}, "mappings": {"Science Fiction": ["Science Fiction", "SF"]}}})
        self.assertEqual(self.src({"goodreads": {"mappings": {}}}), {"goodreads": {"mappings": {}}})
        self.assertIsNone(self.src({"goodreads": {"mappings": "x", "values": []}}))

    def test_goodreads_more_tags(self):
        out = self.src({"goodreads_more_tags": {"values": {"absolute": "7.6", "percentage": 250, "percentageOf": [0, 2, 300], "enabled": False,
                                                           "timeout": 0, "nope": 1}, "mappings": {"sci-fi": ["Science Fiction"]}}})
        self.assertEqual(out, {"goodreads_more_tags": {"values": {"absolute": 8, "percentage": 100, "percentageOf": [1, 2, 100], "enabled": False, "timeout": 0.1},
                                                       "mappings": {"sci-fi": ["Science Fiction"]}}})
        for bad in ([], ["1"], "1, 2", [True]):
            self.assertIsNone(self.src({"goodreads_more_tags": {"values": {"percentageOf": bad}}}), bad)

    def test_mappings(self):
        self.assertIsNone(cp.clean_mappings(["a"]))
        many = {"k%d" % i: ["t%d" % j for j in range(30)] for i in range(1200)}
        out = cp.clean_mappings(many)
        self.assertEqual(len(out), cp.MAX_MAPPINGS)
        self.assertEqual(len(out["k0"]), cp.MAP_TAGS)


class ReadWrite(unittest.TestCase):
    def test_read_adds_the_labels(self):
        with mock.patch.object(cp, "_run", return_value=dict(STATE)) as run:
            out = cp.read()
        self.assertIs(run.call_args.args[0], cp.READ)
        self.assertNotIn("ok", out)
        self.assertEqual(out["labels"]["fields"]["pubdate"], "Published date")
        self.assertIn(["one_of", "is one of"], [list(x) for x in out["labels"]["matches"]])

    def test_write_sends_only_clean_changes(self):
        calls = []
        with mock.patch.object(cp, "_run", side_effect=lambda script, job=None, timeout=90: calls.append((script, job)) or dict(STATE)):
            cp.write({"prefs": {"max_tags": 1000, "bogus": 1, "ignore_fields": ["comments"]}, "sources": {"Google": {"enabled": False}}})
        self.assertEqual(calls[0], (cp.WRITE, {"prefs": {"max_tags": 99, "ignore_fields": ["comments"]}, "sources": {"Google": {"enabled": False}}}))
        self.assertIs(calls[1][0], cp.READ)                 # and the state as Calibre now has it

    def test_run_reads_calibres_answer(self):
        done = SimpleNamespace(stdout="noise\nDAFRESULT " + json.dumps({"ok": False, "error": "Tag rules: “(” isn't a pattern"}), stderr="")
        with mock.patch("subprocess.run", return_value=done), self.assertRaises(cp.PrefsError) as e:
            cp._run(cp.WRITE, {})
        self.assertIn("isn't a pattern", str(e.exception))
        with mock.patch("subprocess.run", return_value=SimpleNamespace(stdout="", stderr="Traceback\nImportError: x")), self.assertRaises(cp.PrefsError):
            cp._run(cp.READ)

    def test_scripts(self):
        for s in (cp.READ, cp.WRITE):
            compile(s, "calibre-script", "exec")
        self.assertIn("enable_plugin(p)", cp.WRITE)
        self.assertIn("disable_plugin(p)", cp.WRITE)
        self.assertIn('msprefs["cover_priorities"] = cp', cp.WRITE)
        self.assertIn("matcher(r, names[key][1])", cp.WRITE)       # the tag mapper's own compile, for tags, publishers, series
        self.assertIn("compile_rules([r])", cp.WRITE)               # and the author mapper's
        self.assertIn("p.prefs[o.name] = v", cp.WRITE)               # a source's options into its own prefs
        self.assertIn("plugin_prefs[STORE_NAME] = new", cp.WRITE)    # the Goodreads plugin's, as its dialog commits
        self.assertIn("c.plugin_prefs.commit()", cp.WRITE)           # Goodreads More Tags' nested settings, written
        keys = re.search(r"keys = \[(.*?)\]", cp.READ, re.S).group(1)
        self.assertEqual(sorted(re.findall(r'"(\w+)"', keys)), sorted(list(cp.BOOLS) + list(cp.INTS) + ["ignore_fields"] + list(cp.RULES)))


class Endpoints(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app

    def test_get(self):
        with mock.patch.object(cp, "read", return_value={"sources": []}):
            self.assertEqual(self.app.get_download_prefs(), {"sources": []})
        with mock.patch.object(cp, "read", side_effect=cp.PrefsError("Calibre didn't answer")), self.assertRaises(HTTPException) as e:
            self.app.get_download_prefs()
        self.assertEqual(e.exception.status_code, 502)

    def test_put(self):
        with mock.patch.object(cp, "write", return_value={"ok": 1}) as w:
            self.assertEqual(self.app.put_download_prefs({"prefs": {"max_tags": 3}}), {"ok": 1})
        self.assertEqual(w.call_args.args[0], {"prefs": {"max_tags": 3}})
        for body in (None, [], {"prefs": [1]}, {"sources": "Google"}):
            with self.assertRaises(HTTPException):
                self.app.put_download_prefs(body)
        with mock.patch.object(cp, "write", side_effect=cp.PrefsError("Tag rules: “(” isn't a pattern")), self.assertRaises(HTTPException) as e:
            self.app.put_download_prefs({"prefs": {}})
        self.assertEqual(e.exception.status_code, 400)


class FindDetails(unittest.TestCase):
    def test_identify_hands_back_the_chosen_fields(self):
        compile(calibrefind.IDENTIFY, "calibre-script", "exec")
        self.assertIn('"ignore_fields": list(msprefs["ignore_fields"])', calibrefind.IDENTIFY)
        answer = {"ok": True, "results": [{"source": "Google", "title": "T", "authors": [], "comments": "<p>x</p>", "identifiers": {}}],
                  "prefs": {"ignore_fields": ["comments", "title"], "append_comments": True}}
        with mock.patch("subprocess.run", return_value=SimpleNamespace(stdout="DAFRESULT " + json.dumps(answer), stderr="")):
            info = {}
            res = calibrefind.calibre_sources("T", [], {}, info=info)
            self.assertEqual(info, {"prefs": {"ignore_fields": ["comments", "title"], "append_comments": True}})
            self.assertEqual(res[0]["comments"], "x")
            self.assertEqual(len(calibrefind.calibre_sources("T", [], {})), 1)      # info is optional

    def test_find_passes_them_on(self):
        def sources(title, authors, ids, info=None, **kw):
            if info is not None:
                info["prefs"] = {"ignore_fields": ["publisher"], "append_comments": False}
            return []
        with mock.patch.object(calibrefind, "calibre_sources", side_effect=sources), mock.patch.object(calibrefind, "hardcover", return_value=[]):
            out = calibrefind.find(lambda: mock.MagicMock(), 1, 1, "T", ["A"], {})
        self.assertEqual(out["prefs"], {"ignore_fields": ["publisher"], "append_comments": False})


if __name__ == "__main__":
    unittest.main()
