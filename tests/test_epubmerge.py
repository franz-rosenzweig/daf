"""EpubMerge (POST /api/catalog/epubmerge): what it hands Calibre, and what it turns away."""
import unittest
from unittest import mock

from fastapi import HTTPException


class EpubMerge(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app
        self.formats = {1: ["EPUB", "PDF"], 2: ["EPUB"], 3: ["MOBI"], 4: ["EPUB"]}
        p = mock.patch("daf.catalog.formats_of", side_effect=lambda cid: self.formats.get(cid, []))
        p.start()
        self.addCleanup(p.stop)

    def post(self, body):
        from daf import calibrewrite
        seen = {}

        def start(fn):
            with mock.patch.object(calibrewrite, "run", side_effect=lambda ops, timeout: seen.update(ops=ops) or {"added": [99]}):
                seen["done"] = fn()
            return "job1"
        with mock.patch.object(calibrewrite, "start_job", side_effect=start):
            out = self.app.post_epubmerge(body)
        return out, seen

    def test_the_books_in_order(self):
        out, seen = self.post({"ids": [4, "2", 1, 4], "title": "  Middlemarch and Others ", "authors": ["George Eliot", " "], "flatten": 1})
        self.assertEqual(out, {"job": "job1"})
        self.assertEqual(seen["done"], 99)
        op = seen["ops"][0]
        self.assertEqual(op["op"], "epubmerge")
        self.assertEqual(op["ids"], [4, 2, 1])               # the order given, each once
        self.assertEqual(op["title"], "Middlemarch and Others")
        self.assertEqual(op["authors"], ["George Eliot"])
        self.assertTrue(op["flatten"])
        self.assertFalse(op["descriptions"])

    def test_empty_title_is_the_plugins(self):
        _out, seen = self.post({"ids": [1, 2]})
        self.assertEqual(seen["ops"][0]["title"], "")
        self.assertEqual(seen["ops"][0]["authors"], [])

    def test_turned_away(self):
        for body in ({"ids": [1]}, {"ids": [1, 1]}, {"ids": []}, {}, None, {"ids": list(range(1, 300))}):
            with self.assertRaises(HTTPException):
                self.post(body)
        with self.assertRaises(HTTPException) as e:
            self.post({"ids": [1, 3]})                     # a book with no EPUB
        self.assertIn("EPUB", e.exception.detail)


class Script(unittest.TestCase):
    def test_the_op_is_in_calibres_script(self):
        from daf import calibrewrite
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        self.assertIn('elif k == "epubmerge"', calibrewrite.SCRIPT)
        self.assertIn("from calibre_plugins.epubmerge.epubmerge import doMerge", calibrewrite.SCRIPT)


if __name__ == "__main__":
    unittest.main()
