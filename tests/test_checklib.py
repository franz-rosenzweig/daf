"""Check library (catalog.check_library) on a made-up Calibre library."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from daf import catalog, config


class CheckLibrary(unittest.TestCase):
    def test_what_doesnt_match(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Path(d)
            db = lib / "metadata.db"
            c = sqlite3.connect(db)
            c.executescript("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT, has_cover BOOL);"
                            "CREATE TABLE data (book INTEGER, format TEXT, name TEXT);")
            rows = [(1, "Whole", "A/Whole (1)", 1), (2, "No File", "A/No File (2)", 0), (3, "Gone File", "B/Gone File (3)", 1), (4, "No Folder", "B/No Folder (4)", 0)]
            c.executemany("INSERT INTO books VALUES (?,?,?,?)", rows)
            c.executemany("INSERT INTO data VALUES (?,?,?)", [(1, "EPUB", "Whole - A"), (3, "EPUB", "Gone File - B")])
            c.commit(); c.close()
            for p in ("A/Whole (1)", "A/No File (2)", "B/Gone File (3)", "B/Stray (9)"):
                (lib / p).mkdir(parents=True)
            (lib / "A/Whole (1)/Whole - A.epub").write_bytes(b"PK")
            (lib / "A/Whole (1)/cover.jpg").write_bytes(b"x")
            (lib / "A/Whole (1)/Extra.mobi").write_bytes(b"x")
            with mock.patch.object(config, "CALIBRE_DBS", [db]):
                r = catalog.check_library()
        self.assertEqual(r["books"], 4)
        self.assertEqual(r["no_files"], [{"id": 2, "title": "No File"}])
        self.assertEqual(r["missing_files"], [{"id": 3, "title": "Gone File", "format": "EPUB"}])
        self.assertEqual(r["missing_cover"], [{"id": 3, "title": "Gone File"}])
        self.assertEqual(r["missing_folder"], [{"id": 4, "title": "No Folder"}])
        self.assertEqual(r["extra_files"], [{"id": 1, "title": "Whole", "file": "Extra.mobi"}])
        self.assertEqual(r["unknown_folders"], [{"path": "B/Stray (9)"}])


if __name__ == "__main__":
    unittest.main()
