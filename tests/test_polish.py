"""Polish books (POST /api/catalog/polish): what it hands Calibre, and what it turns away."""
import unittest
from unittest import mock

from fastapi import HTTPException


class Polish(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app
        self.formats = {1: ["EPUB", "PDF"], 2: ["AZW3", "EPUB"], 3: ["MOBI"], 4: ["EPUB", "ORIGINAL_EPUB"], 5: ["KEPUB"], 6: ["ORIGINAL_AZW3"]}
        p = mock.patch("daf.catalog.formats_of", side_effect=lambda cid: self.formats.get(cid, []))
        p.start()
        self.addCleanup(p.stop)

    def post(self, body):
        from daf import calibrewrite
        seen = {}

        def start(ids, opts, keep):
            seen.update(ids=ids, opts=opts, keep=keep)
            return "job1"
        with mock.patch.object(calibrewrite, "start_polish_many", side_effect=start):
            out = self.app.post_polish(body)
        return out, seen

    def test_the_books_that_can_be_polished(self):
        out, seen = self.post({"ids": [1, "2", 3, 1, 4, 5, 6], "opts": {"smarten_punctuation": True, "subset": True}})
        self.assertEqual(out, {"job": "job1", "total": 5, "skipped": 1})
        self.assertEqual(seen["ids"], [1, 2, 4, 5, 6])          # each once; the MOBI-only book left out
        self.assertTrue(seen["opts"]["smarten_punctuation"])
        self.assertTrue(seen["opts"]["subset"])
        self.assertFalse(seen["opts"]["embed"])
        self.assertEqual(set(seen["opts"]), set(self.app.POLISH_ACTIONS))
        self.assertTrue(seen["keep"])                           # Calibre keeps the original unless told not to

    def test_options(self):
        _out, seen = self.post({"ids": [1], "opts": {"jacket": True, "nonsense": True, "embed": "yes"}, "keep_original": False})
        self.assertTrue(seen["opts"]["jacket"])
        self.assertTrue(seen["opts"]["metadata"])               # a jacket needs the details updated too
        self.assertFalse(seen["opts"]["embed"])                 # only a real true counts
        self.assertNotIn("nonsense", seen["opts"])
        self.assertFalse(seen["keep"])

    def test_turned_away(self):
        for body in ({"ids": [1]}, {"ids": [1], "opts": {}}, {"ids": [1], "opts": {"embed": False}}, {"ids": [], "opts": {"embed": True}},
                     {}, None, {"ids": list(range(1, 600)), "opts": {"embed": True}}, {"ids": [1], "opts": ["embed"]}):
            with self.assertRaises(HTTPException):
                self.post(body)
        with self.assertRaises(HTTPException) as e:
            self.post({"ids": [3], "opts": {"embed": True}})    # no EPUB, AZW3 or KEPUB
        self.assertIn("EPUB", e.exception.detail)


class Job(unittest.TestCase):
    def test_a_book_at_a_time(self):
        from daf import calibrewrite
        calls = []

        def run(ops, timeout):
            calls.append(ops)
            if ops[0]["id"] == 2:
                raise calibrewrite.CalibreError("broken")
            return {}

        class Now:                                              # the job's thread, run right here
            def __init__(self, target, daemon):
                self.target = target

            def start(self):
                self.target()
        with mock.patch.object(calibrewrite, "run", side_effect=run), mock.patch.object(calibrewrite.threading, "Thread", Now):
            jid = calibrewrite.start_polish_many([1, 2, 3], {"embed": True}, True)
        j = calibrewrite.job(jid)
        self.assertEqual([c[0]["id"] for c in calls], [1, 2, 3])
        self.assertEqual(calls[0], [{"op": "polish", "id": 1, "opts": {"embed": True}, "keep_original": True}])
        self.assertEqual((j["running"], j["done"], j["total"]), (False, 3, 3))
        self.assertEqual(j["failed"], [{"id": 2, "error": "broken"}])


class Script(unittest.TestCase):
    def test_the_op_is_in_calibres_script(self):
        from daf import calibrewrite
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        self.assertIn('elif k == "polish"', calibrewrite.SCRIPT)
        self.assertIn("from calibre.ebooks.oeb.polish.main import SUPPORTED, gui_polish", calibrewrite.SCRIPT)
        self.assertIn("d.save_original_format(i, fmt)", calibrewrite.SCRIPT)
        from daf import app
        for a in app.POLISH_ACTIONS:                            # the server's actions are the script's
            self.assertIn('"%s"' % a, calibrewrite.SCRIPT)


if __name__ == "__main__":
    unittest.main()
