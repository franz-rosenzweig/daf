"""Send to Kindle and Save to disk in All books, on a made-up library: the On device column, queueing
Calibre books for the Kindle (ones Daf has no row for yet too), and the zip Save to disk makes from
Calibre's names. Calibre itself isn't run: its names are given."""
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from daf import catalog, config, db, kindlequeue, savetodisk


def daf_conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    return c


def calibre_library(root):
    """Three books: 1 and 2 with an EPUB (2 a PDF and a cover too), 3 with no file."""
    lib = Path(root) / "library"
    lib.mkdir()
    c = sqlite3.connect(lib / "metadata.db")
    c.executescript("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT, has_cover BOOL);"
                    "CREATE TABLE data (id INTEGER PRIMARY KEY, book INTEGER, format TEXT, name TEXT, uncompressed_size INTEGER);")
    c.executemany("INSERT INTO books VALUES (?,?,?,?)", [(1, "A Made Up Novel", "Some Writer/A Made Up Novel (1)", 0),
                                                        (2, "The Second Book", "Other Writer/The Second Book (2)", 1),
                                                        (3, "No File Yet", "Other Writer/No File Yet (3)", 0)])
    c.executemany("INSERT INTO data (book, format, name, uncompressed_size) VALUES (?,?,?,?)",
                  [(1, "EPUB", "A Made Up Novel - Some Writer", 10), (2, "EPUB", "The Second Book - Other Writer", 10),
                   (2, "PDF", "The Second Book - Other Writer", 10)])
    c.commit()
    c.close()
    for p in ("Some Writer/A Made Up Novel (1)", "Other Writer/The Second Book (2)", "Other Writer/No File Yet (3)"):
        (lib / p).mkdir(parents=True)
    (lib / "Some Writer/A Made Up Novel (1)/A Made Up Novel - Some Writer.epub").write_bytes(b"PK one")
    (lib / "Other Writer/The Second Book (2)/The Second Book - Other Writer.epub").write_bytes(b"PK two")
    (lib / "Other Writer/The Second Book (2)/The Second Book - Other Writer.pdf").write_bytes(b"%PDF two")
    (lib / "Other Writer/The Second Book (2)/cover.jpg").write_bytes(b"\xff\xd8\xff cover")
    return lib / "metadata.db"


class OnDevice(unittest.TestCase):
    def test_waiting_and_on_the_kindle(self):
        c = daf_conn()
        self.addCleanup(c.close)
        c.execute("INSERT INTO kindle_files (path, md5, book_id, shelf, seen) VALUES ('Books/One (1).epub', 'a', 'cal:1', 'Books', 100)")
        c.execute("INSERT INTO kindle_files (path, md5, book_id, shelf, seen) VALUES ('Two (6).epub', 'b', 'cal:6', '', 100)")
        rows = [("book:cal:1", "cal:1", "Nightstand", 90, None, None),      # on the Kindle, and sent again since: waiting
                ("book:cal:2", "cal:2", "Books", 150, None, None),          # waiting
                ("book:cal:3", "cal:3", "Books", 120, 200, None),           # delivered after the last report
                ("book:cal:4", "cal:4", "Books", 20, 50, None),             # delivered, then gone from the Kindle
                ("book:cal:5", "cal:5", "Books", 150, None, "too big")]     # the Kindle turned it down
        c.executemany("INSERT INTO kindle_queue (id, kind, ref, name, shelf, path, size, requested, delivered, error) "
                      "VALUES (?, 'book', ?, 'x.epub', ?, '/nowhere', 1, ?, ?, ?)", rows)
        d = kindlequeue.on_device(c)
        self.assertEqual(d["cal:1"], {"state": "Waiting", "shelf": "Nightstand"})
        self.assertEqual(d["cal:2"]["state"], "Waiting")
        self.assertEqual(d["cal:3"], {"state": "Kindle", "shelf": "Books"})
        self.assertEqual(d["cal:6"], {"state": "Kindle", "shelf": ""})
        self.assertNotIn("cal:4", d)
        self.assertNotIn("cal:5", d)

    def test_the_column_is_shown_sorted_and_searched(self):
        c = daf_conn()
        self.addCleanup(c.close)
        c.execute("INSERT INTO books (id, kind, title, calibre_id) VALUES ('cal:1', 'book', 'One', 1)")
        c.execute("INSERT INTO kindle_files (path, md5, book_id, shelf, seen) VALUES ('One (1).epub', 'a', 'cal:1', '', 100)")
        c.execute("INSERT INTO kindle_queue (id, kind, ref, name, shelf, path, size, requested) VALUES ('book:cal:2', 'book', 'cal:2', 'x', 'Books', '/x', 1, 5)")
        books = {i: {"calibre_id": i, "title": t, "title_sort": t, "authors": [], "tags": [], "formats": ["EPUB"]} for i, t in ((1, "One"), (2, "Two"), (3, "Three"))}
        with mock.patch.object(catalog, "calibre_rows", return_value=(books, [])):
            out, cols = catalog.rows(c, {})
        by = {b["calibre_id"]: b["ondevice"] for b in out}
        self.assertEqual(by, {1: "Kindle", 2: "Waiting", 3: None})       # 2 has no Daf row: its id is cal:2 all the same
        self.assertIn({"key": "ondevice", "label": "On device", "type": "text"}, cols)
        found = lambda q: sorted(b["title"] for b in catalog.search(out, q, cols))      # noqa: E731
        self.assertEqual(found("ondevice:true"), ["One", "Two"])
        self.assertEqual(found("ondevice:false"), ["Three"])
        self.assertEqual(found("ondevice:waiting"), ["Two"])
        self.assertEqual(found("on_device:kindle"), ["One"])
        self.assertEqual(found("kindle:>0"), [])                          # kindle is still progress's
        self.assertEqual([b["title"] for b in catalog.sort(out, "ondevice", False, cols)], ["One", "Two", "Three"])


class SendToKindle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbp = calibre_library(self.tmp.name)
        for p in (mock.patch.object(config, "CALIBRE_DBS", [self.dbp]), mock.patch.object(config, "load_settings", return_value={})):
            p.start()
            self.addCleanup(p.stop)
        cal = {1: {"title": "A Made Up Novel", "authors": ["Some Writer"]}, 2: {"title": "The Second Book", "authors": ["Other Writer"]},
               3: {"title": "No File Yet", "authors": ["Other Writer"]}}
        p = mock.patch.object(catalog, "calibre_rows", return_value=(cal, []))
        p.start()
        self.addCleanup(p.stop)
        from daf import app
        self.app = app
        self.c = daf_conn()
        self.addCleanup(self.c.close)
        self.c.execute("INSERT INTO books (id, kind, title, author, calibre_id, private) VALUES ('cal:1', 'book', 'A Made Up Novel', 'Some Writer', 1, 0)")

    def test_the_sheet_shows_each_books_format_and_state(self):
        self.c.execute("INSERT INTO kindle_queue (id, kind, ref, name, shelf, path, size, requested) VALUES ('book:cal:1', 'book', 'cal:1', 'x', 'Books', '/x', 1, 5)")
        r = self.app.get_catalog_kindle("1,2,3,x", c=self.c)
        self.assertEqual(r["shelves"], ["Books", "Nightstand"])          # no report from the Kindle yet: the queue's own two
        self.assertEqual([(b["id"], b["format"]) for b in r["books"]], [(1, "EPUB"), (2, "EPUB"), (3, None)])
        self.assertEqual(r["books"][0]["kindle"], {"state": "Waiting", "shelf": "Books"})
        self.assertIsNone(r["books"][1]["kindle"])

    def test_queues_the_books_calibre_only_ones_too(self):
        r = self.app.post_catalog_kindle({"ids": [1, "2", 3, 2], "shelf": " Nightstand "}, c=self.c)
        self.assertEqual(r["queued"], 2)
        self.assertEqual(r["skipped"], [3])                               # no file
        row = self.c.execute("SELECT id, calibre_id, title, author FROM books WHERE id = 'cal:2'").fetchone()
        self.assertEqual(tuple(row), ("cal:2", 2, "The Second Book", "Other Writer"))     # Daf's row, made for it
        q = {r["id"]: dict(r) for r in self.c.execute("SELECT * FROM kindle_queue")}
        self.assertEqual(set(q), {"book:cal:1", "book:cal:2"})
        self.assertEqual(q["book:cal:2"]["shelf"], "Nightstand")
        self.assertEqual(q["book:cal:2"]["name"], "The Second Book - Other Writer (2).epub")
        self.assertTrue(q["book:cal:2"]["path"].endswith("The Second Book - Other Writer.epub"))
        self.assertIsNone(q["book:cal:2"]["delivered"])
        self.assertEqual(kindlequeue.on_device(self.c)["cal:2"]["state"], "Waiting")

    def test_turned_away(self):
        for body in ({}, {"ids": []}, {"ids": ["x"]}, None):
            with self.assertRaises(HTTPException):
                self.app.post_catalog_kindle(body, c=self.c)
        r = self.app.post_catalog_kindle({"ids": [99]}, c=self.c)        # not in Calibre
        self.assertEqual((r["queued"], r["skipped"]), (0, [99]))
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM kindle_queue").fetchone()[0], 0)

    def test_a_book_calibre_wrote_again_goes_at_its_new_size(self):
        self.app.post_catalog_kindle({"ids": [1]}, c=self.c)
        epub = self.dbp.parent / "Some Writer/A Made Up Novel (1)/A Made Up Novel - Some Writer.epub"
        self.assertEqual(kindlequeue.inbox(self.c)[0]["size"], 6)
        epub.write_bytes(b"PK one, with its details written in")      # as Calibre does after a change to the book's details
        self.assertEqual(kindlequeue.inbox(self.c)[0]["size"], epub.stat().st_size)
        self.assertEqual(self.c.execute("SELECT size FROM kindle_queue WHERE id = 'book:cal:1'").fetchone()[0], epub.stat().st_size)


class Inbox(unittest.TestCase):
    """What the Kindle's plugin is told is waiting: each file at the size it is when the Kindle asks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = daf_conn()
        self.addCleanup(self.c.close)
        self.f = Path(self.tmp.name) / "Some Articles.epub"
        self.f.write_bytes(b"PK articles")
        kindlequeue.queue_file(self.c, self.f)

    def size(self):
        return self.c.execute("SELECT size FROM kindle_queue WHERE id = 'file:Some Articles.epub'").fetchone()[0]

    def test_as_it_was_queued(self):
        self.assertEqual(kindlequeue.inbox(self.c), [{"id": "file:Some Articles.epub", "name": "Some Articles.epub", "shelf": "Daf", "size": 11}])
        self.assertEqual(self.size(), 11)

    def test_a_file_that_grew_is_reported_at_its_new_size(self):
        with open(self.f, "ab") as fh:
            fh.write(b" and a few more bytes")
        self.assertEqual(self.size(), 11)                                 # the row still has the size it was queued at
        self.assertEqual(kindlequeue.inbox(self.c)[0]["size"], 32)
        self.assertEqual(self.size(), 32)                                 # and is put right as the Kindle asks

    def test_a_file_that_shrank(self):
        self.f.write_bytes(b"PK")
        self.assertEqual(kindlequeue.inbox(self.c)[0]["size"], 2)
        self.assertEqual(self.size(), 2)

    def test_a_file_thats_gone_leaves_the_inbox(self):
        self.f.unlink()
        self.assertEqual(kindlequeue.inbox(self.c), [])
        row = self.c.execute("SELECT size, error FROM kindle_queue").fetchone()
        self.assertEqual(tuple(row), (11, "The file isn't on the server any more"))

    def test_one_delivered_is_left_as_it_was(self):
        kindlequeue.done(self.c, "file:Some Articles.epub")
        with open(self.f, "ab") as fh:
            fh.write(b" more")
        self.assertEqual(kindlequeue.inbox(self.c), [])
        self.assertEqual(self.size(), 11)


class Options(unittest.TestCase):
    def test_calibres_defaults(self):
        o = savetodisk.clean({})
        self.assertEqual(o, {"template": "{author_sort}/{title}/{title} - {authors}", "formats": "all", "cover": True, "opf": True,
                             "underscores": False, "ascii": False, "lowercase": False, "single": False})
        self.assertEqual(savetodisk.clean(None), o)

    def test_checked(self):
        o = savetodisk.clean({"template": "  {title}  ", "formats": ["epub", "PDF", "../x", "epub", 7], "cover": 0, "single": 1, "junk": True})
        self.assertEqual(o["template"], "{title}")
        self.assertEqual(o["formats"], ["EPUB", "PDF", "7"])
        self.assertFalse(o["cover"])
        self.assertTrue(o["single"])
        self.assertNotIn("junk", o)
        self.assertEqual(savetodisk.clean({"template": " ", "formats": []})["template"], savetodisk.DEFAULT_TEMPLATE)
        self.assertEqual(savetodisk.clean({"formats": ["../"]})["formats"], "all")


class Names(unittest.TestCase):
    def test_every_name_is_safe(self):
        self.assertEqual(savetodisk.part(".."), "_.")
        self.assertEqual(savetodisk.part("."), "_")
        self.assertEqual(savetodisk.part(""), "_")
        self.assertEqual(savetodisk.part("/etc/passwd"), "_etc_passwd")
        self.assertEqual(savetodisk.part("a\\b\x00c\nd"), "a_b_c_d")
        self.assertEqual(savetodisk.part(".hidden"), "_hidden")
        long = savetodisk.part("é" * 300)
        self.assertLessEqual(len(long.encode("utf-8")), savetodisk.CAP)
        self.assertEqual(long, "é" * (savetodisk.CAP // 2))


class Layout(unittest.TestCase):
    def setUp(self):
        self.lib = {1: {"dir": Path("/lib/a"), "cover": Path("/lib/a/cover.jpg"), "files": {"EPUB": Path("/lib/a/x.epub"), "ORIGINAL_EPUB": Path("/lib/a/x.original_epub")}},
                    2: {"dir": Path("/lib/b"), "cover": None, "files": {"PDF": Path("/lib/b/y.pdf")}},
                    3: {"dir": Path("/lib/c"), "cover": None, "files": {"EPUB": Path("/lib/c/z.epub")}}}
        opf = '<package><guide><reference type="cover" title="Cover" href="%s"/></guide></package>' % savetodisk.COVER_REF
        self.named = {1: {"components": ["Writer, Some", "Novel, A", "Novel, A - Some Writer"], "opf": opf},
                      2: {"components": ["Writer, Other", "Book & Co", "Book & Co - Other Writer"], "opf": "<package/>"},
                      3: {"components": ["writer, some", "novel, a", "novel, a - some writer"], "opf": "<package/>"}}

    def test_calibres_layout(self):
        entries, saved, skipped = savetodisk.layout([1, 2], savetodisk.clean({}), self.lib, self.named)
        names = [n for n, _ in entries]
        self.assertEqual(names, ["Writer, Some/Novel, A/Novel, A - Some Writer.jpg", "Writer, Some/Novel, A/Novel, A - Some Writer.opf",
                                 "Writer, Some/Novel, A/Novel, A - Some Writer.epub", "Writer, Some/Novel, A/Novel, A - Some Writer.original_epub",
                                 "Writer, Other/Book & Co/Book & Co - Other Writer.opf", "Writer, Other/Book & Co/Book & Co - Other Writer.pdf"])
        self.assertIn('href="Novel, A - Some Writer.jpg"', dict(entries)["Writer, Some/Novel, A/Novel, A - Some Writer.opf"])
        self.assertEqual((saved, skipped), ([1, 2], {}))

    def test_formats_cover_and_opf(self):
        o = savetodisk.clean({"formats": ["EPUB"], "cover": False, "opf": False})
        entries, saved, skipped = savetodisk.layout([1, 2], o, self.lib, self.named)
        self.assertEqual([n for n, _ in entries], ["Writer, Some/Novel, A/Novel, A - Some Writer.epub"])
        self.assertEqual(skipped, {2: "Requested formats not available"})
        _e, _s, skipped = savetodisk.layout([2], savetodisk.clean({"cover": False, "opf": False}), {2: dict(self.lib[2], files={})}, self.named)
        self.assertEqual(skipped, {2: "Nothing to save"})

    def test_one_name_twice(self):
        o = savetodisk.clean({"single": True, "opf": False, "cover": False})
        named = {1: {"components": ["Novel, A - Some Writer"]}, 3: {"components": ["novel, a - some writer"]}}
        entries, saved, _ = savetodisk.layout([1, 3], o, self.lib, named)
        self.assertEqual([n for n, _ in entries][-1], "novel, a - some writer (2).epub")     # a Mac doesn't tell case apart
        self.assertEqual(saved, [1, 3])

    def test_odd_names_from_a_template(self):
        named = {1: {"components": ["..", "/abs", "  ", ".hidden"], "opf": None}}
        entries, _s, _k = savetodisk.layout([1], savetodisk.clean({"cover": False, "opf": False, "formats": ["EPUB"]}), self.lib, named)
        self.assertEqual([n for n, _ in entries], ["_./_abs/_hidden.epub"])
        for n, _ in entries:
            self.assertFalse(n.startswith("/"))
            self.assertNotIn("..", n.split("/"))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dbp = calibre_library(self.tmp.name)
        for p in (mock.patch.object(config, "CALIBRE_DBS", [dbp]), mock.patch.object(config, "STATE", Path(self.tmp.name) / "state")):
            p.start()
            self.addCleanup(p.stop)

    def names(self, cids, covers, opts, timeout=300):
        self.asked = (list(cids), list(covers), opts)
        return ({1: {"components": ["Writer, Some", "Made Up Novel, A", "Made Up Novel, A - Some Writer"], "opf": "<package/>"},
                 2: {"components": ["Writer, Other", "Second Book, The", "Second Book, The - Other Writer"], "opf": "<package/>"}},
                {3: "x"} if 3 in cids else {})

    def test_the_zip(self):
        with mock.patch.object(savetodisk, "names", side_effect=self.names):
            r = savetodisk.build([1, 2, 3], savetodisk.clean({}))
        self.assertEqual(self.asked[:2], ([1, 2, 3], [2]))                # the covers that are there
        self.assertEqual((r["books"], r["skipped"], r["name"]), (2, [3], "2 books.zip"))
        p, name = savetodisk.ready(r["file"])
        self.assertEqual(p.parent, Path(self.tmp.name))
        with zipfile.ZipFile(p) as z:
            self.assertEqual(sorted(z.namelist()), [
                "Writer, Other/Second Book, The/Second Book, The - Other Writer.epub",
                "Writer, Other/Second Book, The/Second Book, The - Other Writer.jpg",
                "Writer, Other/Second Book, The/Second Book, The - Other Writer.opf",
                "Writer, Other/Second Book, The/Second Book, The - Other Writer.pdf",
                "Writer, Some/Made Up Novel, A/Made Up Novel, A - Some Writer.epub",
                "Writer, Some/Made Up Novel, A/Made Up Novel, A - Some Writer.opf"])
            self.assertEqual(z.read("Writer, Other/Second Book, The/Second Book, The - Other Writer.pdf"), b"%PDF two")
        savetodisk.forget(r["file"])
        self.assertFalse(p.exists())
        self.assertEqual(savetodisk.ready(r["file"]), (None, None))
        self.assertEqual(savetodisk.ready("../../etc"), (None, None))

    def test_one_book_is_named_for_itself(self):
        with mock.patch.object(savetodisk, "names", side_effect=self.names):
            r = savetodisk.build([1], savetodisk.clean({"formats": ["PDF", "EPUB"]}))
        self.assertEqual(r["name"], "Made Up Novel, A - Some Writer.zip")
        savetodisk.forget(r["file"])

    def test_nothing_to_save(self):
        with mock.patch.object(savetodisk, "names", side_effect=self.names), self.assertRaises(RuntimeError) as e:
            savetodisk.build([1, 2], savetodisk.clean({"formats": ["MOBI"]}))
        self.assertIn("Requested formats not available", str(e.exception))
        with mock.patch.object(savetodisk, "names", return_value=({}, {1: "Failed to calculate path for save to disk"})), self.assertRaises(RuntimeError) as e:
            savetodisk.build([1], savetodisk.clean({"template": "{title"}))
        self.assertIn("Failed to calculate path", str(e.exception))
        self.assertEqual(list(Path(self.tmp.name).glob("daf-save-*.zip")), [])


class Routes(unittest.TestCase):
    def setUp(self):
        from daf import app
        self.app = app

    def test_save_starts_a_job_with_the_options(self):
        from daf import calibrewrite
        seen = {}
        with mock.patch.object(calibrewrite, "start_job", side_effect=lambda fn: seen.update(done=fn()) or "job1"), \
                mock.patch.object(savetodisk, "build", side_effect=lambda cids, opts: seen.update(cids=cids, opts=opts) or {"file": "f"}):
            out = self.app.post_catalog_save({"ids": [3, "1", 3, "x"], "formats": ["epub"], "underscores": True})
        self.assertEqual(out, {"job": "job1"})
        self.assertEqual(seen["cids"], [3, 1])
        self.assertEqual(seen["opts"]["formats"], ["EPUB"])
        self.assertTrue(seen["opts"]["underscores"])
        with self.assertRaises(HTTPException):
            self.app.post_catalog_save({"ids": []})

    def test_a_zip_thats_gone(self):
        with self.assertRaises(HTTPException) as e:
            self.app.get_catalog_save("0123456789abcdef")
        self.assertEqual(e.exception.status_code, 404)


class Script(unittest.TestCase):
    def test_calibres_own_code_on_a_copy(self):
        compile(savetodisk.SCRIPT, "save-script", "exec")
        for s in ("get_path_components", "metadata_to_opf", "preprocess_template", "?mode=ro", ".backup(", "mkdtemp"):
            self.assertIn(s, savetodisk.SCRIPT)
        self.assertNotIn("set_field", savetodisk.SCRIPT)


if __name__ == "__main__":
    unittest.main()
