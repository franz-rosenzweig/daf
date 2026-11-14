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
        out = cp.clean({"prefs": {"cover_priorities": {"Google": 9}, "id_link_rules": {"x": "y"}, "author_map_rules": [], "user_default_ignore_fields": [],
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
        self.assertIn("compile_pat(r[\"query\"])", cp.WRITE)      # the tag mapper's own regex flavour
        keys = re.search(r"keys = \[(.*?)\]", cp.READ, re.S).group(1)
        self.assertEqual(sorted(re.findall(r'"(\w+)"', keys)), sorted(list(cp.BOOLS) + list(cp.INTS) + ["ignore_fields", "tag_map_rules"]))


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
