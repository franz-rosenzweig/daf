"""What Daf keeps up in Calibre (daf/calibrekeep.py): the Read column and page counts."""
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from daf import calibrekeep, config

ENUM = json.dumps({"enum_values": ["Reading\U0001F4D6", "Planning", "Paused", "Maybe", "Finished", "Dropped", "--"]})


def calibre(path, rows):
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE custom_columns (id INTEGER, label TEXT, datatype TEXT, display TEXT);"
                    "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT);"
                    "CREATE TABLE custom_column_4 (id INTEGER PRIMARY KEY, value TEXT);"
                    "CREATE TABLE books_custom_column_4_link (book INTEGER, value INTEGER);")
    c.execute("INSERT INTO custom_columns VALUES (4, 'read', 'enumeration', ?)", (ENUM,))
    vals = {}
    for cid, title, v in rows:
        c.execute("INSERT INTO books VALUES (?, ?)", (cid, title))
        if v:
            if v not in vals:
                vals[v] = c.execute("INSERT INTO custom_column_4 (value) VALUES (?)", (v,)).lastrowid
            c.execute("INSERT INTO books_custom_column_4_link VALUES (?, ?)", (cid, vals[v]))
    c.commit()
    c.close()


def daf(statuses, seen=None):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE books (calibre_id INTEGER, status TEXT)")
    c.execute("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT)")
    c.executemany("INSERT INTO books VALUES (?, ?)", statuses)
    if seen is not None:
        c.execute("INSERT INTO kv VALUES ('calibre_read_seen', ?)", (json.dumps(seen),))
    return c


class ReadColumn(unittest.TestCase):
    def test_choices_by_name(self):
        self.assertEqual(calibrekeep.read_choices(ENUM), {"to-read": "Planning", "reading": "Reading\U0001F4D6", "read": "Finished",
                                                          "paused": "Paused", "dropped": "Dropped"})

    def plan(self, rows, statuses, seen=None):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "metadata.db"
            calibre(db, rows)
            with mock.patch.object(config, "CALIBRE_DBS", [db]):
                return calibrekeep.read_plan(daf(statuses, seen), {})

    def test_fills_blanks_follows_changes_and_leaves_disagreements(self):
        rows = [(1, "Blank", None), (2, "Dashes", "--"), (3, "Same", "Finished"), (4, "Maybe", "Maybe"), (5, "Disagrees", "Dropped"), (6, "Changed in Daf", "Planning")]
        statuses = [(1, "reading"), (2, "to-read"), (3, "read"), (4, "to-read"), (5, "to-read"), (6, "read")]
        changes, seen, conflicts, key = self.plan(rows, statuses, seen={"6": "to-read", "5": "to-read"})
        self.assertEqual(key, "#read")
        self.assertEqual(changes, {"Reading\U0001F4D6": [1], "Planning": [2], "Finished": [6]})
        self.assertEqual([x["id"] for x in conflicts], [5])
        self.assertEqual(seen["6"], "read")

    def test_first_look_changes_nothing_that_disagrees(self):
        changes, _seen, conflicts, _key = self.plan([(6, "Was planned", "Planning")], [(6, "read")])
        self.assertEqual(changes, {})
        self.assertEqual(conflicts[0]["calibre"], "Planning")


class KOReaderColumns(unittest.TestCase):
    def test_progress_and_status_only_where_they_differ(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "metadata.db"
            calibre(db, [(1, "A", None), (2, "B", None), (3, "C", None), (4, "D", None)])
            c = sqlite3.connect(db)
            c.executescript("INSERT INTO custom_columns VALUES (7, 'ko_progfloat', 'float', '{}');"
                            "INSERT INTO custom_columns VALUES (8, 'ko_status', 'text', '{}');"
                            "CREATE TABLE custom_column_7 (id INTEGER PRIMARY KEY, book INTEGER, value REAL);"
                            "CREATE TABLE custom_column_8 (id INTEGER PRIMARY KEY, book INTEGER, value TEXT);"
                            "INSERT INTO custom_column_7 (book, value) VALUES (1, 0.2501), (2, 0.1);"
                            "INSERT INTO custom_column_8 (book, value) VALUES (1, 'reading'), (3, 'reading');")
            c.commit(); c.close()
            dc = sqlite3.connect(":memory:")
            dc.execute("CREATE TABLE books (calibre_id INTEGER, status TEXT, progress REAL)")
            dc.executemany("INSERT INTO books VALUES (?, ?, ?)", [(1, "reading", 25.0), (2, "read", 100.0), (3, "to-read", 0.7), (4, "paused", 40.0), (9, "reading", 5.0)])
            with mock.patch.object(config, "CALIBRE_DBS", [db]):
                ops = calibrekeep.ko_plan(dc, {})
        got = {o["ids"][0]: o["fields"] for o in ops}
        self.assertNotIn(1, got)                                   # the same already
        self.assertEqual(got[2], {"#ko_progfloat": 1.0, "#ko_status": "complete"})
        self.assertEqual(got[3], {"#ko_progfloat": 0.007})         # To read: the status is left alone
        self.assertEqual(got[4], {"#ko_progfloat": 0.4, "#ko_status": "abandoned"})
        self.assertNotIn(9, got)                                   # not in this library


class Pages(unittest.TestCase):
    def test_counts_the_text(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
            z.writestr("OEBPS/content.opf", '<package><manifest><item id="a" href="a.xhtml"/><item href="b.xhtml" id="b"/></manifest>'
                                            '<spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
            z.writestr("OEBPS/a.xhtml", "<html><head><style>p{}</style></head><body><p>" + "x" * 3000 + "</p></body></html>")
            z.writestr("OEBPS/b.xhtml", "<html><body><p>" + "y" * 2000 + "</p></body></html>")
        with tempfile.NamedTemporaryFile(suffix=".epub") as f:
            f.write(buf.getvalue()); f.flush()
            self.assertEqual(calibrekeep.epub_pages(f.name), 3)        # 5,000 characters, 2,170 a page


if __name__ == "__main__":
    unittest.main()
