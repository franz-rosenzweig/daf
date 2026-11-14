"""Restore the originals (POST /api/catalog/restore-original, POST /api/catalog/book/{id}/files/{fmt}/restore):
what they hand Calibre, and what they turn away."""
import unittest
from unittest import mock

from fastapi import HTTPException


class RestoreOriginal(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app
        self.formats = {1: ["EPUB", "ORIGINAL_EPUB"], 2: ["EPUB"], 3: ["AZW3", "EPUB", "ORIGINAL_AZW3", "ORIGINAL_EPUB"], 4: ["ORIGINAL_MOBI"]}
        p = mock.patch("daf.catalog.formats_of", side_effect=lambda cid: self.formats.get(cid, []))
        p.start()
        self.addCleanup(p.stop)

    def post(self, body):
        from daf import calibrewrite
        seen = {}
        with mock.patch.object(calibrewrite, "start_restore_many", side_effect=lambda ids: seen.update(ids=ids) or "job1"):
            out = self.app.post_restore_original(body)
        return out, seen

    def test_the_books_with_originals(self):
        out, seen = self.post({"ids": [1, "2", 3, 1, 4]})
        self.assertEqual(out, {"job": "job1", "total": 3, "skipped": 1})
        self.assertEqual(seen["ids"], [1, 3, 4])                # each once; the one without an ORIGINAL_ left out

    def test_turned_away(self):
        for body in ({"ids": []}, {}, None, {"ids": list(range(1, 600))}):
            with self.assertRaises(HTTPException):
                self.post(body)
        with self.assertRaises(HTTPException) as e:
            self.post({"ids": [2]})                             # nothing to restore
        self.assertIn("ORIGINAL_", e.exception.detail)

    def test_one_file(self):
        with mock.patch.object(self.app, "_calibre") as cal:
            out = self.app.restore_catalog_file(3, "original_azw3")
        self.assertEqual(out, {"ok": True, "format": "AZW3"})
        self.assertEqual(cal.call_args[0][0], [{"op": "restore_original", "id": 3, "fmts": ["ORIGINAL_AZW3"]}])
        for cid, fmt in ((3, "EPUB"), (2, "ORIGINAL_EPUB"), (1, "ORIGINAL_AZW3")):
            with mock.patch.object(self.app, "_calibre") as cal, self.assertRaises(HTTPException):
                self.app.restore_catalog_file(cid, fmt)
            cal.assert_not_called()

    def test_the_job(self):
        from daf import calibrewrite
        with mock.patch.object(calibrewrite, "start_each", return_value="j") as each:
            self.assertEqual(calibrewrite.start_restore_many([5, 6]), "j")
        self.assertEqual(each.call_args[0][0], [{"op": "restore_original", "id": 5}, {"op": "restore_original", "id": 6}])


class Script(unittest.TestCase):
    def test_the_op_is_in_calibres_script(self):
        from daf import calibrewrite
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        self.assertIn('elif k == "restore_original"', calibrewrite.SCRIPT)
        self.assertIn("d.restore_original_format(i, f)", calibrewrite.SCRIPT)


if __name__ == "__main__":
    unittest.main()
