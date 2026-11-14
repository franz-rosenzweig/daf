"""Calibre's highlights both ways, on a made-up library: Daf's own reader highlights written into
Calibre's annotations in Calibre's own terms (calibreannots.py), the import leaving those alone,
and Calibre's bookmarks as Daf's (calibrehl.import_bookmarks). Calibre itself isn't run."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from daf import calibreannots as A, calibrewrite, config
from daf.sources import calibrehl as H
from tests.test_calibrehl import TWO, ann, daf_conn, make_epub

TWO_ID = TWO.replace("<p>A plain line", '<p id="x">A plain line')


def hl(cfi, text, **k):
    return {"id": k.get("id", "e1"), "text": text, "chapter": k.get("chapter", "Second Chapter"), "color": k.get("color"),
            "user_note": k.get("note"), "pos": json.dumps({"cfi": cfi, "fraction": 0.7, **k.get("pos", {})})}


class ToCalibre(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.epub = Path(self.tmp.name) / "book.epub"
        make_epub(self.epub, TWO_ID)

    def calibre(self, cfi, text, **k):
        return A.annotation(self.epub, hl(cfi, text, **k), "made-up-uuid")

    def test_calibres_own_shape(self):
        a = self.calibre("epubcfi(/6/4!/4/6,/1:2,/1:12)", "plain line", color="pink", note="A note typed in Daf")
        self.assertEqual(a, {"type": "highlight", "uuid": "made-up-uuid", "highlighted_text": "plain line",
                             "start_cfi": "/2/4/6[x]/1:2", "end_cfi": "/2/4/6[x]/1:12", "spine_index": 1, "spine_name": "OEBPS/Text/two b.xhtml",
                             "style": {"type": "builtin", "kind": "color", "which": "red"}, "toc_family_titles": ["Second Chapter"],
                             "notes": "A note typed in Daf"})

    def test_calibres_offsets(self):
        # Calibre counts across all of the paragraph's own text, past the <span>: the reader's /3:1 is Calibre's /1:19
        a = self.calibre("epubcfi(/6/4!/4/4,/3:1,/3:20)", "came after the rain")
        self.assertEqual((a["start_cfi"], a["end_cfi"]), ("/2/4/4/1:19", "/2/4/4/1:38"))
        a = self.calibre("epubcfi(/6/4!/4/4,/2/1:0,/3:5)", "Quiet words came")
        self.assertEqual((a["start_cfi"], a["end_cfi"]), ("/2/4/4/2/1:0", "/2/4/4/1:23"))

    def test_text_right_after_an_element(self):
        # /1:18 would be read by Calibre as the end of "The lamp was low. ", taking in the span's words: the end of the span's text instead
        a = self.calibre("epubcfi(/6/4!/4/4,/3:0,/3:5)", " came")
        self.assertEqual((a["start_cfi"], a["end_cfi"]), ("/2/4/4/2/1:11", "/2/4/4/1:23"))
        a = self.calibre("epubcfi(/6/4!/4/4,/1:4,/1:18)", "lamp was low.")
        self.assertEqual(a["end_cfi"], "/2/4/4/1:18")                     # the end of a text before an element is Calibre's own reading

    def test_ending_at_an_element(self):
        a = self.calibre("epubcfi(/6/4!/4,/4/1:0,/6)", "The lamp was low. Quiet words came after the rain, and the  garden slept.")
        self.assertEqual((a["start_cfi"], a["end_cfi"]), ("/2/4/4/1:0", "/2/4/4/1:62"))

    def test_read_back_the_same(self):
        for cfi, text in (("epubcfi(/6/4!/4/6,/1:2,/1:12)", "plain line"), ("epubcfi(/6/4!/4/4,/3:1,/3:20)", "came after the rain"),
                          ("epubcfi(/6/4!/4/4,/3:0,/3:5)", " came")):
            a = self.calibre(cfi, text)
            bk = H._book(self.epub)
            root, _text, at = H._doc(self.epub, bk, 1)
            mine, back = A.parse_cfi(cfi), A.parse_cfi(H.place(self.epub, a)["cfi"])
            self.assertEqual([A._spec_at(root, at, p) for p in back[1:]], [A._spec_at(root, at, p) for p in mine[1:]], cfi)
            self.assertEqual([A.calibre_reads(root, at, a[k]) for k in ("start_cfi", "end_cfi")], [A._spec_at(root, at, p) for p in mine[1:]])

    def test_not_sent(self):
        self.assertIsNone(self.calibre("epubcfi(/6/4!/4/6,/1:2,/1:12)", "other words"))        # the file has changed since
        self.assertIsNone(self.calibre("epubcfi(/6/8!/4/6,/1:2,/1:12)", "plain line"))         # no such chapter
        self.assertIsNone(self.calibre("pdf:3:0.1,0.2", "plain line"))
        self.assertIsNone(self.calibre("epubcfi(/6/4!/4/6,/1:2,/1:12)", "plain line", pos={"pdf": {"pg": 1}}))

    def test_parse(self):
        self.assertEqual(A.parse_cfi("epubcfi(/6/4!/4/2[c3]/7:0)")[1], [(4, None, None), (2, "c3", None), (7, None, 0)])
        self.assertEqual(A.parse_cfi("epubcfi(/6/4!/4,/36[a]/2/1:0,/38)")[2], [(4, None, None), (38, None, None)])
        for bad in (None, "", "epubcfi(/6/4)", "epubcfi(/6/4!/4,/1:0)", "nonsense"):
            self.assertIsNone(A.parse_cfi(bad))


class Push(unittest.TestCase):
    """plan() and push() over a made-up Daf database and library, with Calibre's run stood in for."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        lib = Path(self.tmp.name) / "library"
        for d in ("A/One (1)", "A/Two (2)"):
            (lib / d).mkdir(parents=True)
        make_epub(lib / "A/One (1)/One - A.epub")
        (lib / "A/Two (2)/Two - A.pdf").write_bytes(b"%PDF")
        self.dbp = lib / "metadata.db"
        c = sqlite3.connect(self.dbp)
        c.executescript("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT); CREATE TABLE data (book INTEGER, format TEXT, name TEXT);"
                        "INSERT INTO books VALUES (1, 'One', 'A/One (1)'), (2, 'Two', 'A/Two (2)');"
                        "INSERT INTO data VALUES (1, 'EPUB', 'One - A'), (2, 'PDF', 'Two - A');")
        c.commit()
        c.close()
        p = mock.patch.object(config, "CALIBRE_DBS", [self.dbp])
        p.start()
        self.addCleanup(p.stop)
        self.c = daf_conn()
        self.addCleanup(self.c.close)
        self.c.executemany("INSERT INTO books (id, kind, title, calibre_id, private) VALUES (?, 'book', ?, ?, 0)", [("cal:1", "One", 1), ("cal:2", "Two", 2)])
        rows = [("e1", "cal:1", "epub", "plain line", '{"cfi": "epubcfi(/6/4!/4/6,/1:2,/1:12)"}', 1735787045),
                ("e2", "cal:1", "epub", "came after the rain", '{"cfi": "epubcfi(/6/4!/4/4,/3:1,/3:20)"}', 1735787046),
                ("e3", "cal:2", "epub", "a PDF line", '{"cfi": "pdf:1:0.1,0.1,0.2,0.2", "pdf": {"pg": 1}}', 1735787047),
                ("k1", "cal:1", "kindle", "plain line", None, 1735787048)]
        self.c.executemany("INSERT INTO highlights (id, book_id, source, text, pos, created, seen, deleted) VALUES (?, ?, ?, ?, ?, ?, 0, 0)", rows)
        self.runs = []
        p = mock.patch.object(calibrewrite, "run", side_effect=lambda ops, timeout=120: self.runs.append(ops) or {})
        p.start()
        self.addCleanup(p.stop)

    def test_only_daf_reader_highlights_in_an_epub(self):
        self.assertEqual(A.push(self.c), 2)
        (ops,) = self.runs
        self.assertEqual([(o["op"], o["id"], o["fmt"]) for o in ops], [("annotations", 1, "EPUB")])
        annots = ops[0]["annots"]
        self.assertEqual({a["uuid"] for a in annots}, {H.daf_uuid("e1"), H.daf_uuid("e2")})
        self.assertEqual(annots[0]["timestamp"], "2025-01-02T03:04:05.000Z")          # when it was made in Daf
        self.assertEqual(len(H.daf_uuid("e1")), 22)

    def test_a_second_sync_sends_nothing(self):
        A.push(self.c)
        self.assertEqual(A.push(self.c), 0)
        self.assertEqual(len(self.runs), 1)

    def test_changes_and_removals_follow(self):
        A.push(self.c)
        self.c.execute("INSERT INTO review_state (hl_id, status, user_note) VALUES ('e1', 'noted', 'A note')")
        self.c.execute("UPDATE highlights SET color = 'blue' WHERE id = 'e1'")
        self.c.execute("UPDATE highlights SET deleted = 1 WHERE id = 'e2'")
        self.assertEqual(A.push(self.c), 2)
        by = {a["uuid"]: a for a in self.runs[-1][0]["annots"]}
        e1, e2 = by[H.daf_uuid("e1")], by[H.daf_uuid("e2")]
        self.assertEqual((e1["notes"], e1["style"]["which"]), ("A note", "blue"))
        self.assertNotEqual(e1["timestamp"], "2025-01-02T03:04:05.000Z")               # newer than what Calibre has
        self.assertEqual(set(e2), {"type", "uuid", "removed", "timestamp"})            # as Calibre's viewer removes one
        self.assertTrue(e2["removed"])
        self.assertEqual(A.push(self.c), 0)
        self.c.execute("DELETE FROM highlights WHERE id = 'e1'")                         # gone from Daf altogether
        A.push(self.c)
        self.assertEqual(self.runs[-1][0]["annots"], [{"type": "highlight", "uuid": H.daf_uuid("e1"), "removed": True, "timestamp": self.runs[-1][0]["annots"][0]["timestamp"]}])

    def test_the_import_leaves_them_alone(self):
        A.push(self.c)
        c = sqlite3.connect(self.dbp)
        c.execute("CREATE TABLE annotations (id INTEGER PRIMARY KEY, book INTEGER, format TEXT, user_type TEXT, user TEXT, timestamp REAL, "
                  "annot_id TEXT, annot_type TEXT, annot_data TEXT)")
        mine = dict(self.runs[0][0]["annots"][0], highlighted_text="plain line")
        theirs = ann("/2/4/6/1:2", "/2/4/6/1:12", "plain line", uuid="made-in-calibre")
        gone = dict(theirs, uuid="sent-before")                                         # one Daf sent whose highlight Daf no longer has
        self.c.execute("INSERT INTO calibre_pushed (hl_id, uuid, cal_id, fmt, hash, at) VALUES ('old', 'sent-before', 1, 'EPUB', 'x', 0)")
        c.executemany("INSERT INTO annotations (book, format, user_type, user, timestamp, annot_id, annot_type, annot_data) VALUES (1, 'EPUB', 'local', 'viewer', 0, ?, 'highlight', ?)",
                      [(a["uuid"], json.dumps(a)) for a in (mine, theirs, gone)])
        c.commit()
        c.close()
        rows = H.rows(self.c, {})
        self.assertEqual([json.loads(r["pos"])["calibre"] for r in rows], ["made-in-calibre"])

    def test_the_op_is_calibres(self):
        compile(calibrewrite.SCRIPT, "calibre-script", "exec")
        self.assertIn('elif k == "annotations"', calibrewrite.SCRIPT)
        self.assertIn('merge_annotations_for_book(ids[0], op["fmt"].upper(), op["annots"], user_type="local", user="viewer")', calibrewrite.SCRIPT)


class Bookmarks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        lib = Path(self.tmp.name) / "library"
        (lib / "A/One (1)").mkdir(parents=True)
        make_epub(lib / "A/One (1)/One - A.epub")
        self.dbp = lib / "metadata.db"
        c = sqlite3.connect(self.dbp)
        c.executescript("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT); CREATE TABLE data (book INTEGER, format TEXT, name TEXT);"
                        "INSERT INTO books VALUES (1, 'One', 'A/One (1)'); INSERT INTO data VALUES (1, 'EPUB', 'One - A');"
                        "CREATE TABLE annotations (id INTEGER PRIMARY KEY, book INTEGER, format TEXT, user_type TEXT, user TEXT, timestamp REAL, "
                        "annot_id TEXT, annot_type TEXT, annot_data TEXT, UNIQUE(book, user_type, user, format, annot_type, annot_id));")
        c.commit()
        c.close()
        p = mock.patch.object(config, "CALIBRE_DBS", [self.dbp])
        p.start()
        self.addCleanup(p.stop)
        self.c = daf_conn()
        self.addCleanup(self.c.close)
        self.c.execute("INSERT INTO books (id, kind, title, calibre_id, private) VALUES ('cal:1', 'book', 'One', 1, 0)")
        self.c.execute("INSERT INTO book_marks (id, book_id, cfi, fraction, chapter, created) VALUES ('mown', 'cal:1', 'epubcfi(/6/2!/4/2)', 0.1, 'Mine', 1)")
        self.put("Where the rain starts", "epubcfi(/4/2/4/4/1:19)")
        self.put("A whole paragraph", "epubcfi(/4/2/4/6)")
        self.put("Nowhere now", "epubcfi(/4/2/4/40/1:0)")
        self.put("In an AZW3", "epubcfi(/4/2/4/6)", fmt="AZW3")

    def put(self, title, pos, fmt="EPUB", **more):
        c = sqlite3.connect(self.dbp)
        d = {"type": "bookmark", "title": title, "pos": pos, "pos_type": "epubcfi", "timestamp": "2025-03-04T05:06:07.000Z", **more}
        c.execute("INSERT OR REPLACE INTO annotations (book, format, user_type, user, timestamp, annot_id, annot_type, annot_data) "
                  "VALUES (1, ?, 'local', 'viewer', 0, ?, 'bookmark', ?)", (fmt, title, json.dumps(d)))
        c.commit()
        c.close()

    def marks(self):
        return {r["chapter"]: dict(r) for r in self.c.execute("SELECT * FROM book_marks WHERE calibre IS NOT NULL")}

    def test_into_daf(self):
        self.assertEqual(H.import_bookmarks(self.c, {}), 3)
        m = self.marks()
        self.assertEqual(set(m), {"Where the rain starts", "A whole paragraph", "Nowhere now"})     # not the AZW3's: Daf reads the EPUB
        self.assertEqual(m["Where the rain starts"]["cfi"], "epubcfi(/6/4!/4/4/3:1)")              # Calibre's /1:19 is the reader's /3:1
        self.assertTrue(m["Where the rain starts"]["excerpt"].startswith("came after the rain"))
        self.assertEqual(m["A whole paragraph"]["cfi"], "epubcfi(/6/4!/4/6)")
        self.assertEqual(m["Nowhere now"]["cfi"], "epubcfi(/6/4!/4)")                              # not in this file: the chapter's start
        self.assertEqual(m["Where the rain starts"]["created"], 1741064767)
        self.assertTrue(0.5 < m["Where the rain starts"]["fraction"] < 1)
        self.assertEqual(H.import_bookmarks(self.c, {}), 3)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM book_marks").fetchone()[0], 4)

    def test_removed_in_calibre_and_taken_out_in_daf(self):
        H.import_bookmarks(self.c, {})
        self.put("Where the rain starts", "epubcfi(/4/2/4/4/1:19)", removed=True)
        from daf import app
        app.delete_ebook_bookmark("cal:1", self.marks()["A whole paragraph"]["id"], c=self.c)
        self.assertEqual(H.import_bookmarks(self.c, {}), 1)
        self.assertEqual(set(self.marks()), {"Nowhere now"})
        self.assertEqual(self.c.execute("SELECT chapter FROM book_marks WHERE id = 'mown'").fetchone()[0], "Mine")    # Daf's own stays
        c = sqlite3.connect(self.dbp)
        c.execute("DELETE FROM annotations WHERE annot_id = 'A whole paragraph'")
        c.commit()
        c.close()
        H.import_bookmarks(self.c, {})
        self.assertEqual(json.loads(self.c.execute("SELECT v FROM kv WHERE k = ?", (H.GONE_KEY,)).fetchone()[0]), [])   # forgotten once Calibre has none


if __name__ == "__main__":
    unittest.main()
