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
                            "CREATE TABLE data (book INTEGER, format TEXT, name TEXT);"
                            "CREATE TABLE comments (book INTEGER, text TEXT);"
                            "CREATE TABLE identifiers (book INTEGER, type TEXT, val TEXT);"
                            "CREATE TABLE books_languages_link (book INTEGER, lang_code INTEGER);"
                            "CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);"
                            "CREATE TABLE books_authors_link (book INTEGER, author INTEGER);"
                            "CREATE TABLE custom_columns (id INTEGER, label TEXT, datatype TEXT);"
                            "CREATE TABLE custom_column_6 (book INTEGER, value INTEGER);"
                            "INSERT INTO custom_columns VALUES (6, 'pages', 'int');"
                            "INSERT INTO comments VALUES (1, '<p>About it</p>');"
                            "INSERT INTO identifiers VALUES (1, 'isbn', '9780000000001');"
                            "INSERT INTO books_languages_link VALUES (1, 1);"
                            "INSERT INTO authors VALUES (1, 'A. Writer'), (2, 'Unknown');"
                            "INSERT INTO books_authors_link VALUES (1, 1), (3, 2);"
                            "INSERT INTO custom_column_6 VALUES (1, 300);")
            rows = [(1, "Whole", "A/Whole (1)", 1), (2, "No File", "A/No File (2)", 0), (3, "GONE FILE", "B/Gone File (3)", 1), (4, "No Folder", "B/No Folder (4)", 0)]
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
        self.assertEqual(r["missing_files"], [{"id": 3, "title": "GONE FILE", "format": "EPUB"}])
        self.assertEqual(r["missing_cover"], [{"id": 3, "title": "GONE FILE"}])
        self.assertEqual(r["missing_folder"], [{"id": 4, "title": "No Folder"}])
        self.assertEqual(r["extra_files"], [{"id": 1, "title": "Whole", "file": "Extra.mobi"}])
        self.assertEqual(r["unknown_folders"], [{"path": "B/Stray (9)"}])
        # what Quality Check looks at
        self.assertEqual([x["id"] for x in r["no_description"]], [3, 2, 4])
        self.assertEqual([x["id"] for x in r["no_isbn"]], [3, 2, 4])
        self.assertEqual([x["id"] for x in r["no_pages"]], [3])          # only books with a file
        self.assertEqual([x["id"] for x in r["caps_title"]], [3])
        self.assertEqual([x["id"] for x in r["unknown_author"]], [3])


if __name__ == "__main__":
    unittest.main()
