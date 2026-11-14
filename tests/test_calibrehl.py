"""Calibre's own highlights in Daf (daf/sources/calibrehl.py), on a made-up library: an EPUB with two
chapters and annotations the way Calibre's viewer keeps them. Their places become the reader's CFIs
only where the words are really there; the import follows Calibre's edits and removals."""
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from daf import catalog, config, db, ebooks, vaultnotes
from daf.sources import calibrehl, highlights

CONTAINER = ('<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
             '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
OPF = ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0"><metadata/><manifest>'
       '<item id="c1" href="Text/one.xhtml" media-type="application/xhtml+xml"/><item id="c2" href="Text/two%20b.xhtml" media-type="application/xhtml+xml"/>'
       '</manifest><spine toc="ncx"><itemref idref="c1"/><itemref idref="c2"/></spine></package>')
ONE = ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title></head>'
       '<body><h1>First Chapter</h1><p>Nothing much happens here yet.</p></body></html>')
TWO = ('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>Two</title></head>'
       '<body><h1>Second Chapter</h1><p>The lamp was low. <span>Quiet words</span> came after the rain, and the <!-- x --> garden slept.</p>'
       '<p>A plain line about nothing at all.</p></body></html>')


def make_epub(path, two=TWO):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", CONTAINER)
        z.writestr("OEBPS/content.opf", OPF)
        z.writestr("OEBPS/Text/one.xhtml", ONE)
        z.writestr("OEBPS/Text/two b.xhtml", two)


def ann(start, end, text, spine=1, name="OEBPS/Text/two b.xhtml", **more):
    return {"type": "highlight", "uuid": more.pop("uuid", "u-" + start), "start_cfi": start, "end_cfi": end, "highlighted_text": text,
            "spine_index": spine, "spine_name": name, "style": {"kind": "color", "type": "builtin", "which": "yellow"},
            "timestamp": "2025-01-02T03:04:05.000Z", "toc_family_titles": ["Second Chapter"], **more}


class Place(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.epub = Path(self.tmp.name) / "book.epub"
        make_epub(self.epub)

    def test_one_chunk(self):
        p = calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line"))
        self.assertEqual(p["cfi"], "epubcfi(/6/4!/4/6,/1:2,/1:12)")
        self.assertEqual(p["sec"], 1)
        self.assertTrue(0.5 < p["fraction"] < 1)                       # in the second of two chapters

    def test_calibres_offsets_run_across_the_parents_text(self):
        # Calibre counts "/1:19" across all of the paragraph's own text, past the <span>: the spec's /3:1
        p = calibrehl.place(self.epub, ann("/2/4/4/1:19", "/2/4/4/1:38", "came after the rain"))
        self.assertEqual(p["cfi"], "epubcfi(/6/4!/4/4,/3:1,/3:20)")
        p = calibrehl.place(self.epub, ann("/2/4/4/1:40", "/2/4/4/1:61", "and the   garden slept"))     # over the comment
        self.assertEqual(p["cfi"], "epubcfi(/6/4!/4/4,/3:22,/3:43)")

    def test_from_inside_an_element(self):
        p = calibrehl.place(self.epub, ann("/2/4/4/2/1:0", "/2/4/4/1:23", "Quiet words came"))
        self.assertEqual(p["cfi"], "epubcfi(/6/4!/4/4,/2/1:0,/3:5)")

    def test_at_the_edge_of_an_element(self):
        # offset 18 is both the end of "The lamp was low. " and the start of the text after the span
        p = calibrehl.place(self.epub, ann("/2/4/4/1:18", "/2/4/4/1:23", " came"))
        self.assertEqual(p["cfi"], "epubcfi(/6/4!/4/4,/3:0,/3:5)")
        p = calibrehl.place(self.epub, ann("/2/4/4/1:4", "/2/4/4/1:18", "lamp was low."))
        self.assertEqual(p["cfi"], "epubcfi(/6/4!/4/4,/1:4,/1:18)")

    def test_left_to_the_words(self):
        self.assertEqual(calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/6/1:12", "other words")), {"sec": 1})     # the book changed since
        self.assertEqual(calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/9/1:12", "plain line")), {"sec": 1})      # no such place
        self.assertEqual(calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", name="OEBPS/x.xhtml")), {})
        self.assertEqual(calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", spine=7)), {})
        self.assertEqual(calibrehl.place(Path(self.tmp.name) / "none.epub", ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line")), {})

    def test_a_changed_file_is_read_again(self):
        self.assertIn("cfi", calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line")))
        make_epub(self.epub, TWO.replace("A plain line", "A level line"))
        import os
        os.utime(self.epub, ns=(1, 1))
        self.assertEqual(calibrehl.place(self.epub, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line")), {"sec": 1})


class Colours(unittest.TestCase):
    def test_calibres_styles(self):
        b = lambda w: {"kind": "color", "type": "builtin", "which": w}          # noqa: E731
        self.assertEqual([calibrehl.color(b(w)) for w in ("yellow", "green", "blue", "red", "purple", "odd")],
                         ["yellow", "green", "blue", "pink", "purple", "yellow"])
        self.assertEqual(calibrehl.color({"kind": "decoration", "type": "builtin", "which": "wavy"}), "yellow")
        custom = lambda h: calibrehl.color({"kind": "color", "type": "custom", "light": h, "dark": "#000000"})    # noqa: E731
        self.assertEqual([custom(h) for h in ("#7fd17f", "#7fa8ff", "#ff8fa3", "#c58cff", "#ffe066", "#cccccc")],
                         ["green", "blue", "pink", "purple", "yellow", "yellow"])
        self.assertEqual(calibrehl.color(None), "yellow")


def daf_conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    c.executescript(db.TRIGGERS)
    return c


class Import(unittest.TestCase):
    """highlights.import_all with Calibre the only source there is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        lib = root / "library"
        (lib / "A Writer/A Made Up Book (1)").mkdir(parents=True)
        (lib / "A Writer/Another Book (2)").mkdir(parents=True)
        make_epub(lib / "A Writer/A Made Up Book (1)/A Made Up Book - A Writer.epub")
        make_epub(lib / "A Writer/Another Book (2)/Another Book - A Writer.epub")
        self.dbp = lib / "metadata.db"
        c = sqlite3.connect(self.dbp)
        c.executescript("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT, has_cover BOOL, pubdate TEXT, series_index REAL);"
                        "CREATE TABLE data (id INTEGER PRIMARY KEY, book INTEGER, format TEXT, name TEXT);"
                        "CREATE TABLE comments (book INTEGER, text TEXT); CREATE TABLE languages (id INTEGER PRIMARY KEY, lang_code TEXT);"
                        "CREATE TABLE books_languages_link (book INTEGER, lang_code INTEGER, item_order INTEGER);"
                        "CREATE TABLE series (id INTEGER PRIMARY KEY, name TEXT); CREATE TABLE books_series_link (book INTEGER, series INTEGER);"
                        "CREATE TABLE annotations (id INTEGER PRIMARY KEY, book INTEGER NOT NULL, format TEXT NOT NULL COLLATE NOCASE, "
                        "user_type TEXT NOT NULL, user TEXT NOT NULL, timestamp REAL NOT NULL, annot_id TEXT NOT NULL, annot_type TEXT NOT NULL, "
                        "annot_data TEXT NOT NULL, searchable_text TEXT NOT NULL DEFAULT '');")
        c.executemany("INSERT INTO books VALUES (?,?,?,0,NULL,1)", [(1, "A Made Up Book", "A Writer/A Made Up Book (1)"), (2, "Another Book", "A Writer/Another Book (2)")])
        c.executemany("INSERT INTO data (book, format, name) VALUES (?, 'EPUB', ?)", [(1, "A Made Up Book - A Writer"), (2, "Another Book - A Writer")])
        c.commit()
        c.close()
        self.put(1, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", uuid="aaa", notes="A note typed in Calibre"))
        self.put(1, ann("/2/4/4/1:19", "/2/4/4/1:38", "came after the rain", uuid="bbb", style={"kind": "color", "type": "builtin", "which": "red"}))
        self.put(2, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", uuid="ccc"))
        self.put(1, {"type": "bookmark", "title": "A place", "pos": "epubcfi(/6/4!/4/6)", "pos_type": "epubcfi", "uuid": "ddd"}, kind="bookmark")
        for p in (mock.patch.object(config, "CALIBRE_DBS", [self.dbp]), mock.patch.object(config, "VAULT", root / "no-vault"),
                  mock.patch.object(config, "KOINSIGHT_DB", root / "none.db"), mock.patch.object(config, "KARAKEEP_DB", root / "none.db"),
                  mock.patch.object(config, "ABS_DB", root / "none.db"), mock.patch("daf.library.sidecars", return_value=[]),
                  mock.patch.object(highlights, "time", mock.Mock(time=self.clock)),
                  mock.patch.object(catalog, "calibre_rows", return_value=({2: {"title": "Another Book", "authors": ["A Writer"]}}, []))):
            p.start()
            self.addCleanup(p.stop)
        self.c = daf_conn()
        self.addCleanup(self.c.close)
        self.c.execute("INSERT INTO books (id, kind, title, author, calibre_id, private) VALUES ('cal:1', 'book', 'A Made Up Book', 'A Writer', 1, 0)")

    now = 1767225600

    def clock(self):                                    # each sync a little later than the last (its "seen")
        Import.now += 1
        return Import.now

    def put(self, book, data, kind="highlight"):
        c = sqlite3.connect(self.dbp)
        c.execute("INSERT OR REPLACE INTO annotations (id, book, format, user_type, user, timestamp, annot_id, annot_type, annot_data) "
                  "VALUES ((SELECT id FROM annotations WHERE annot_id = ?), ?, 'EPUB', 'local', 'viewer', 1735787045, ?, ?, ?)",
                  (data["uuid"], book, data["uuid"], kind, json.dumps(data)))
        c.commit()
        c.close()

    def drop(self, uuid):
        c = sqlite3.connect(self.dbp)
        c.execute("DELETE FROM annotations WHERE annot_id = ?", (uuid,))
        c.commit()
        c.close()

    def sync(self):
        highlights.import_all(self.c, {"home_tz": "UTC"})
        return {r["id"]: dict(r) for r in self.c.execute("SELECT * FROM highlights WHERE source = 'calibre'")}

    def test_the_highlights_come_in(self):
        h = self.sync()
        self.assertEqual(len(h), 3)                                     # the bookmark isn't a highlight
        a = h[calibrehl.hid(1, "aaa")]
        self.assertEqual((a["book_id"], a["text"], a["note"], a["chapter"], a["color"], a["deleted"]),
                         ("cal:1", "plain line", "A note typed in Calibre", "Second Chapter", "yellow", 0))
        self.assertEqual(a["created"], 1735787045)
        pos = json.loads(a["pos"])
        self.assertEqual((pos["cfi"], pos["sec"], pos["calibre"], pos["format"]), ("epubcfi(/6/4!/4/6,/1:2,/1:12)", 1, "aaa", "EPUB"))
        self.assertEqual(h[calibrehl.hid(1, "bbb")]["color"], "pink")
        c = h[calibrehl.hid(2, "ccc")]
        self.assertEqual(c["book_id"], "cal:2")                          # Daf's row for it, made first
        self.assertEqual(self.c.execute("SELECT calibre_id, title FROM books WHERE id = 'cal:2'").fetchone()[:], (2, "Another Book"))

    def test_again_is_the_same(self):
        first = self.sync()
        again = self.sync()
        self.assertEqual(set(first), set(again))
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM highlights").fetchone()[0], 3)
        for k in first:
            self.assertEqual({x: first[k][x] for x in ("text", "note", "pos", "color", "deleted")}, {x: again[k][x] for x in ("text", "note", "pos", "color", "deleted")})

    def test_changes_in_calibre_follow(self):
        self.sync()
        a = calibrehl.hid(1, "aaa")
        self.c.execute("UPDATE highlights SET color = 'blue' WHERE id = ?", (a,))         # recoloured in Daf
        h = self.sync()
        self.assertEqual(h[a]["color"], "blue")                                         # Calibre's hasn't changed: Daf's stays
        self.put(1, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", uuid="aaa", notes="Changed", style={"kind": "color", "type": "builtin", "which": "green"}))
        h = self.sync()
        self.assertEqual((h[a]["note"], h[a]["color"]), ("Changed", "green"))

    def test_removed_in_calibre(self):
        self.sync()
        self.put(1, {"removed": True, "type": "highlight", "uuid": "aaa", "timestamp": "2025-02-01T00:00:00.000Z"})    # Calibre's stub
        self.drop("bbb")
        h = self.sync()
        self.assertEqual(h[calibrehl.hid(1, "aaa")]["deleted"], 1)
        self.assertEqual(h[calibrehl.hid(1, "bbb")]["deleted"], 1)
        self.assertEqual(h[calibrehl.hid(2, "ccc")]["deleted"], 0)
        self.put(1, ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", uuid="aaa"))           # back again
        self.assertEqual(self.sync()[calibrehl.hid(1, "aaa")]["deleted"], 0)

    def test_calibre_unreadable_removes_nothing(self):
        self.sync()
        with mock.patch.object(config, "CALIBRE_DBS", [Path(self.tmp.name) / "gone.db"]), self.assertLogs("daf.calibrehl", "ERROR"):
            h = self.sync()
        self.assertEqual({v["deleted"] for v in h.values()}, {0})

    def test_the_reader_gets_the_place(self):
        self.sync()
        d = ebooks.details(self.c, "cal:1")
        got = {h["text"]: (h["sec"], h["ccfi"]) for h in d["other_highlights"] if h["source"] == "calibre"}
        self.assertEqual(got, {"plain line": (1, "epubcfi(/6/4!/4/6,/1:2,/1:12)"), "came after the rain": (1, "epubcfi(/6/4!/4/4,/3:1,/3:20)")})

    def test_written_into_the_book_note(self):
        h = [{"id": "c1", "text": "plain line", "note": None, "pos": None, "source": "calibre", "page": None, "chapter": "Second Chapter", "tags": None}]
        out = vaultnotes._render({}, [], [], {"home_tz": "UTC"}, h)
        self.assertIn("**Read in Calibre** · Second Chapter\n> plain line ^daf-h", out)

    def test_a_source_on_the_highlights_page(self):
        from daf import app
        self.assertEqual(app.HL_SOURCES["calibre"], "h.source = 'calibre'")


if __name__ == "__main__":
    unittest.main()
