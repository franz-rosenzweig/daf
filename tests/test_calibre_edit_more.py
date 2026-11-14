"""Books dropped on the Tag browser, Trim cover, and the details inside a book's file: what each hands Calibre."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from fastapi import HTTPException  # noqa: E402


class Drop(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app, self.ops = app, []
        for name, fn in (("_calibre", lambda ops, timeout=120: self.ops.extend(ops)), ("_item_field", lambda f: f if f in ("tags", "series", "authors", "#mood") else (_ for _ in ()).throw(HTTPException(400, "no")))):
            p = mock.patch.object(app, name, side_effect=fn)
            p.start()
            self.addCleanup(p.stop)

    def test_names_and_ratings(self):
        self.app.post_catalog_drop({"ids": [1, "2", "x"], "field": "tags", "value": " Poetry "})
        self.assertEqual(self.ops[-1], {"op": "drop", "ids": [1, 2], "field": "tags", "value": "Poetry"})
        self.app.post_catalog_drop({"ids": [3], "field": "rating", "value": 9})
        self.assertEqual(self.ops[-1]["value"], 5.0)

    def test_turned_away(self):
        for b in ({"ids": [], "field": "tags", "value": "x"}, {"ids": [1], "field": "formats", "value": "EPUB"},
                  {"ids": [1], "field": "tags", "value": " "}, {"ids": [1], "field": "rating", "value": "lots"}, None):
            with self.assertRaises(HTTPException):
                self.app.post_catalog_drop(b)

    def test_trim(self):
        self.app.trim_catalog_cover(4)
        self.assertEqual(self.ops, [{"op": "trim_cover", "ids": [4]}])


class FileMeta(unittest.TestCase):
    def test_the_files_path_inside_calibres_container(self):
        from daf import app, calibrefind, config
        lib = config.CALIBRE_DBS[0].parent
        f = mock.MagicMock()
        f.exists.return_value = True
        f.relative_to.return_value = Path("Some One/A Book (7)/A Book - Some One.epub")
        with mock.patch("daf.catalog.book_file", return_value=f), mock.patch.object(calibrefind, "file_meta", return_value={"title": "A Book"}) as fm:
            self.assertEqual(app.get_catalog_filemeta(7, "epub"), {"title": "A Book"})
        f.relative_to.assert_called_once_with(lib)
        self.assertTrue(fm.call_args[0][0].endswith("/Some One/A Book (7)/A Book - Some One.epub"))
        self.assertEqual(fm.call_args[0][1], "EPUB")
        with mock.patch("daf.catalog.book_file", return_value=None), self.assertRaises(HTTPException):
            app.get_catalog_filemeta(7, "pdf")

    def test_scripts(self):
        from daf import calibrefind, calibrewrite
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        compile(calibrefind.FILEMETA, "filemeta", "exec")
        for k in ('elif k == "drop"', 'elif k == "trim_cover"'):
            self.assertIn(k, calibrewrite.SCRIPT)


if __name__ == "__main__":
    unittest.main()
