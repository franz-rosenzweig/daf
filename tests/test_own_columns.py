"""Add your own columns (POST/PUT/DELETE /api/catalog/columns): what each hands Calibre, and what it turns away."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from fastapi import HTTPException  # noqa: E402


class OwnColumns(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app, self.ops = app, []
        p = mock.patch.object(app, "_calibre", side_effect=lambda ops, timeout=120: self.ops.extend(ops))
        p.start()
        self.addCleanup(p.stop)

    def test_kinds(self):
        self.assertEqual(self.app.post_catalog_column({"label": "#Mood", "heading": " Mood ", "type": "*text"}), {"key": "#mood"})
        self.assertEqual(self.ops[-1], {"op": "create_column", "label": "mood", "heading": "Mood", "datatype": "text", "multiple": True, "display": {"is_names": False}})
        self.app.post_catalog_column({"label": "lent", "heading": "Lent to", "type": "enumeration", "values": ["Sam", " ", "Sam", "Ida"]})
        self.assertEqual(self.ops[-1]["display"], {"enum_values": ["Sam", "Ida"], "enum_colors": []})
        self.app.post_catalog_column({"label": "stars2", "heading": "Stars", "type": "rating"})
        self.assertEqual((self.ops[-1]["datatype"], self.ops[-1]["multiple"]), ("rating", False))

    def test_turned_away(self):
        for b in ({"label": "9lives", "heading": "x", "type": "text"}, {"label": "a b", "heading": "x", "type": "text"},
                  {"label": "ok", "heading": " ", "type": "text"}, {"label": "ok", "heading": "x", "type": "composite"},
                  {"label": "ok", "heading": "x", "type": "enumeration"}, None):
            with self.assertRaises(HTTPException):
                self.app.post_catalog_column(b)
        self.assertEqual(self.ops, [])

    def test_heading_and_delete(self):
        self.app.put_catalog_column("#Mood", {"heading": "Feeling"})
        self.app.delete_catalog_column("mood")
        self.assertEqual(self.ops, [{"op": "column_heading", "label": "mood", "heading": "Feeling"}, {"op": "delete_column", "label": "mood"}])
        with self.assertRaises(HTTPException):
            self.app.put_catalog_column("mood", {"heading": ""})

    def test_script(self):
        from daf import calibrewrite
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        self.assertIn('"create_column", "column_heading", "column_template", "delete_column"', calibrewrite.SCRIPT)


if __name__ == "__main__":
    unittest.main()
