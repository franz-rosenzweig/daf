"""Columns built from other columns (composite.py, /api/catalog/columns): reading them, their values, making them."""
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from fastapi import HTTPException  # noqa: E402

from daf import composite  # noqa: E402


class Composite(unittest.TestCase):
    def test_columns(self):
        c = sqlite3.connect(":memory:")
        c.execute("CREATE TABLE custom_columns (id, label, name, datatype, is_multiple, display, mark_for_delete)")
        c.executemany("INSERT INTO custom_columns VALUES (?,?,?,?,?,?,?)", [
            (1, "who", "Who", "composite", 0, '{"composite_template": "{title} by {authors}"}', 0),
            (2, "gone", "Gone", "composite", 0, "{}", 1), (3, "mood", "Mood", "text", 1, "{}", 0)])
        self.assertEqual(composite.columns(c), [{"id": 1, "key": "#who", "label": "Who", "template": "{title} by {authors}", "multi": False}])

    def test_cells(self):
        self.assertEqual(composite.cell("a, b ,", True), ["a", "b"])
        self.assertEqual(composite.cell(["x", " "], True), ["x"])
        self.assertIsNone(composite.cell("", False))
        self.assertEqual(composite.cell("One by Two", False), "One by Two")

    def test_first_time_waits_then_in_the_background(self):
        cols = [{"key": "#who", "multi": False}]
        composite._state.update(key=None, values={}, busy=False)

        def fake(key, cs):
            composite._state.update(key=key, values={"#who": {1: key}}, busy=False)
        with mock.patch.object(composite, "_compute", side_effect=fake) as comp, mock.patch("threading.Thread") as th:
            self.assertEqual(composite.values("k1", cols), {"#who": {1: "k1"}})        # nothing yet: worked out now
            comp.assert_called_once()
            self.assertEqual(composite.values("k1", cols), {"#who": {1: "k1"}})        # the same library: nothing to do
            self.assertEqual(comp.call_count, 1)
            self.assertEqual(composite.values("k2", cols), {"#who": {1: "k1"}})        # changed: the last ones, the new ones on the way
            th.assert_called_once()
        self.assertEqual(composite.values("k9", []), {})


class Endpoints(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app, self.ops = app, []
        p = mock.patch.object(app, "_calibre", side_effect=lambda ops, timeout=120: self.ops.extend(ops))
        p.start()
        self.addCleanup(p.stop)

    def test_make_and_change(self):
        self.app.post_catalog_column({"label": "who", "heading": "Who", "type": "composite", "template": " {title} by {authors} "})
        op = self.ops[-1]
        self.assertEqual((op["datatype"], op["multiple"], op["display"]["composite_template"], op["display"]["make_category"]), ("composite", False, "{title} by {authors}", False))
        self.app.post_catalog_column({"label": "alltags", "heading": "All tags", "type": "*composite", "template": "{tags}"})
        self.assertEqual((self.ops[-1]["multiple"], self.ops[-1]["display"]["make_category"]), (True, True))
        with self.assertRaises(HTTPException):
            self.app.post_catalog_column({"label": "who2", "heading": "Who", "type": "composite", "template": " "})
        self.app.put_catalog_column("#who", {"template": "{title}"})
        self.assertEqual(self.ops[-1], {"op": "column_template", "label": "who", "template": "{title}"})
        with self.assertRaises(HTTPException):
            self.app.put_catalog_column("who", {"template": ""})


if __name__ == "__main__":
    unittest.main()
