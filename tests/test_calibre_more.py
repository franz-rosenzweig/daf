"""More of Calibre's main window in All books: Mark books (marked:true), Generate cover, and the
bulk "Generate covers" — what each hands Calibre, on made-up books."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import catalog  # noqa: E402


class Marks(unittest.TestCase):
    def setUp(self):
        self.s = {"catalog_marks": [3, 7]}
        for name, fn in (("load_settings", lambda: self.s), ("save_settings", lambda s: self.s.update(s))):
            p = mock.patch("daf.config." + name, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)
        from daf import app
        self.app = app

    def test_add_remove_clear(self):
        r = self.app.put_catalog_marks({"add": [7, "9", "x", 11], "remove": [3]})
        self.assertEqual(r["marks"], [7, 9, 11])                  # no doubles, no junk, in the order marked
        self.assertEqual(catalog.marked(self.s), [7, 9, 11])
        r = self.app.put_catalog_marks({"clear": True, "add": [2]})
        self.assertEqual(r["marks"], [2])
        self.assertEqual(self.app.put_catalog_marks(None)["marks"], [2])

    def test_marked_is_searchable(self):
        cols = catalog.columns([])
        books = [{"title": "One", "marked": True}, {"title": "Two", "marked": False}]
        self.assertEqual([b["title"] for b in catalog.search(books, "marked:true", cols)], ["One"])
        self.assertEqual([b["title"] for b in catalog.search(books, "not marked:true", cols)], ["Two"])
        self.assertIn("marked", {c["key"] for c in cols})


class SortSeveral(unittest.TestCase):
    def test_then_by(self):
        cols = catalog.columns([])
        books = [{"title": t, "title_sort": t, "authors": [a], "author_sort": a, "series": s, "series_sort": s, "series_index": i, "rating": r}
                 for t, a, s, i, r in [("C", "Bee", "Saga", 2, 3), ("A", "Bee", "Saga", 1, None), ("B", "Ant", None, None, 5), ("D", "Bee", None, None, 3)]]
        order = lambda key, desc=False, then=(): [b["title"] for b in catalog.sort(books, key, desc, cols, then)]
        self.assertEqual(order("authors", then=[("series", False)]), ["B", "A", "C", "D"])      # no series last, within the author
        self.assertEqual(order("authors", True, [("title", True)]), ["D", "C", "A", "B"])
        self.assertEqual(order("rating", True, [("title", False)]), ["B", "C", "D", "A"])     # no rating last
        self.assertEqual(catalog.parse_then("series:1,nope:0,title:0,series:0", cols), [("series", True), ("title", False)])


class MarksKept(unittest.TestCase):
    def test_settings_keep_the_marks(self):
        import json
        import tempfile
        from daf import config
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text(json.dumps({"catalog_marks": [4, "x", 9]}))
            with mock.patch.object(config, "SETTINGS_PATH", p):
                self.assertEqual(config.load_settings()["catalog_marks"], [4, 9])


class Covers(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app

    def test_generate_previews_from_the_books_details(self):
        from daf import calibrefind
        d = {"title": "A Made Up Title", "authors": ["Some Author"], "series": "A Series", "series_index": 2.0, "publisher": "A Press"}
        with mock.patch("daf.catalog.details", return_value=d), \
                mock.patch.object(calibrefind, "gencovers_start", return_value="abc123def456") as start:
            out = self.app.gen_catalog_covers(5, c=None)
        self.assertEqual(out, {"job": "abc123def456"})
        cid, book = start.call_args[0]
        self.assertEqual(cid, 5)
        self.assertEqual(book, d)

    def test_unknown_book(self):
        from fastapi import HTTPException
        with mock.patch("daf.catalog.details", return_value=None), self.assertRaises(HTTPException):
            self.app.gen_catalog_covers(5, c=None)

    def test_bulk_generates_after_the_other_changes(self):
        seen = {}
        with mock.patch.object(self.app, "_calibre", side_effect=lambda ops, timeout=120: seen.update(ops=ops, timeout=timeout)), \
                mock.patch.object(self.app, "_custom_keys", return_value=set()):
            self.app.bulk_catalog({"ids": [1, 2], "fields": {"publisher": "A Press"}, "gencover": True})
        self.assertEqual([o["op"] for o in seen["ops"]], ["set", "gencover"])
        self.assertEqual(seen["ops"][-1]["ids"], [1, 2])
        with mock.patch.object(self.app, "_calibre", side_effect=lambda ops, timeout=120: seen.update(ops=ops)), \
                mock.patch.object(self.app, "_custom_keys", return_value=set()):
            self.app.bulk_catalog({"ids": [1], "gencover": True})
        self.assertEqual([o["op"] for o in seen["ops"]], ["gencover"])

    def test_remove_covers(self):
        seen = {}
        with mock.patch.object(self.app, "_calibre", side_effect=lambda ops, timeout=120: seen.update(ops=ops)), \
                mock.patch.object(self.app, "_custom_keys", return_value=set()):
            self.app.bulk_catalog({"ids": [1, 2], "remove_covers": True})
            self.assertEqual(seen["ops"], [{"op": "remove_covers", "ids": [1, 2]}])
            self.app.bulk_catalog({"ids": [1, 2], "remove_covers": True, "gencover": True})     # a new cover wins
            self.assertEqual([o["op"] for o in seen["ops"]], ["gencover"])
            self.app.delete_catalog_cover(7)
            self.assertEqual(seen["ops"], [{"op": "remove_covers", "ids": [7]}])

    def test_scripts(self):
        from daf import calibrefind, calibrewrite
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        compile(calibrefind.GENCOVERS, "gencovers", "exec")
        self.assertIn('elif k == "gencover"', calibrewrite.SCRIPT)
        self.assertIn('elif k == "remove_covers"', calibrewrite.SCRIPT)
        self.assertIn("gencover", calibrewrite.EMBED_AFTER)


if __name__ == "__main__":
    unittest.main()
