"""Edit book's Check spelling and Reports (ebooktools.py): what goes to Calibre, Change all's
checkpoint, what's turned away."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from fastapi import HTTPException  # noqa: E402

from daf import ebookedit as E, ebooktools as T  # noqa: E402


class Copy(unittest.TestCase):
    """A working copy of a made-up book in a folder of the test's own."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(E, "EDIT_DIR", Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)
        book = Path(tmp.name) / "5" / "book" / "OEBPS"
        book.mkdir(parents=True)
        (book / "ch1.xhtml").write_text("<p>recieve</p>")
        (Path(tmp.name) / "5" / "meta.json").write_text(json.dumps({"fmt": "EPUB", "changed": False}))


class Ops(Copy):
    def test_each_op_and_its_job(self):
        seen = []
        with mock.patch.object(T, "_run", side_effect=lambda cid, job, timeout=900: seen.append(job) or {"words": []}):
            T.spell(5)
            T.suggest(5, " recieve ", "eng-US")
            T.add_word(5, "Daf", "eng")
            T.reports(5)
        self.assertEqual([j["op"] for j in seen], ["spell", "suggest", "add_word", "reports"])
        self.assertEqual(seen[0]["max_locs"], T.MAX_LOCS)
        self.assertEqual((seen[1]["word"], seen[1]["lang"]), ("recieve", "eng-US"))

    def test_turned_away(self):
        for w in ("", " ", "a<b", "x" * 300, None, "two\nlines"):
            with self.assertRaises(E.EditError):
                T._word(w)
        for lang in ("", "en us", "e/n", None):
            with self.assertRaises(E.EditError):
                T._lang(lang)
        with self.assertRaises(E.EditError):
            T.spell(6)                                          # no copy of that book open

    def test_change_all_keeps_a_checkpoint_when_it_changed_something(self):
        with mock.patch.object(T, "_run", return_value={"changed": ["OEBPS/ch1.xhtml"], "recognized": True}) as run:
            out = T.change_all(5, "recieve", "receive", "eng")
        self.assertEqual(run.call_args[0][1], {"op": "change", "word": "recieve", "to": "receive", "lang": "eng"})
        self.assertEqual(out["checkpoint"], 1)
        self.assertEqual([c["label"] for c in E.checkpoints(5)], ["Change all"])
        self.assertTrue(E.meta(5)["changed"])

    def test_change_all_drops_it_when_nothing_changed_or_it_failed(self):
        with mock.patch.object(T, "_run", return_value={"changed": [], "recognized": None}):
            out = T.change_all(5, "nothing", "else", "eng")
        self.assertNotIn("checkpoint", out)
        with mock.patch.object(T, "_run", side_effect=E.EditError("Calibre said no")), self.assertRaises(E.EditError):
            T.change_all(5, "recieve", "receive", "eng")
        self.assertEqual(E.checkpoints(5), [])
        self.assertFalse(E.meta(5)["changed"])


class Run(Copy):
    def test_the_answer_and_a_refusal(self):
        ok = mock.Mock(stdout="Integration status: True\nDAFRESULT " + json.dumps({"ok": True, "words": [["x", "eng", 1, True, False, []]]}), stderr="")
        with mock.patch.object(T.subprocess, "run", return_value=ok) as run:
            out = T._run(5, {"op": "spell"})
        self.assertEqual(out, {"words": [["x", "eng", 1, True, False, []]]})
        job = json.loads(run.call_args.kwargs["input"])
        self.assertTrue(job["dir"].endswith("/5"))                 # the copy as calibre-debug sees it
        bad = mock.Mock(stdout="DAFRESULT " + json.dumps({"ok": False, "error": "No OPF"}), stderr="")
        with mock.patch.object(T.subprocess, "run", return_value=bad), self.assertRaises(E.EditError) as e:
            T._run(5, {"op": "spell"})
        self.assertEqual(str(e.exception), "No OPF")
        with mock.patch.object(T.subprocess, "run", return_value=mock.Mock(stdout="", stderr="boom")), self.assertRaises(E.EditError):
            T._run(5, {"op": "spell"})


class Routes(Copy):
    def test_change_all_route(self):
        from daf import app
        with mock.patch.object(app, "_ebx_job", return_value={"job": "j"}) as job:
            self.assertEqual(app.post_ebookedit_change_all(5, {"word": "recieve", "to": "receive", "lang": "eng"}), {"job": "j"})
        self.assertEqual(job.call_args[0][1:], (5, "recieve", "receive", "eng"))
        for b in ({"word": "recieve", "to": "", "lang": "eng"}, {"word": "a<b>", "to": "x", "lang": "eng"}, {"word": "x", "to": "y"}, None):
            with self.assertRaises(HTTPException):
                app.post_ebookedit_change_all(5, b)
        with self.assertRaises(HTTPException):
            app.post_ebookedit_spell(6)                             # nothing open


class Script(unittest.TestCase):
    def test_calibres_own_code(self):
        compile(T.SCRIPT, "calibre-script", "exec")
        for s in ('op == "spell"', 'op == "suggest"', 'op == "add_word"', 'op == "change"', 'op == "reports"',
                  "from calibre.ebooks.oeb.polish.spell import get_all_words, replace_word",
                  "from calibre.ebooks.oeb.polish.report import gather_data", "d.add_to_user_dictionary(name",
                  "d.suggestions(", "d.recognized(w, loc)"):
            self.assertIn(s, T.SCRIPT)


if __name__ == "__main__":
    unittest.main()
