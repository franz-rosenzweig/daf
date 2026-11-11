"""excerpt.at: the lines from where you left off, for the new look's Today (made-up text, no real books)."""
import sqlite3
import unittest
from unittest import mock

from daf import excerpt

TEXT = ("The first sentence is short. The second one is where the reader stopped, in the middle of a thought "
        "that goes on for a while. " + "Then the text carries on with more of the same kind of words. " * 12)


def conn(private=0, progress=None, pos=None):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE books (id TEXT, private INTEGER, progress REAL)")
    c.execute("CREATE TABLE book_positions (book_id TEXT, cfi TEXT, fraction REAL)")
    c.execute("INSERT INTO books VALUES ('cal:1', ?, ?)", (private, progress))
    if pos is not None:
        c.execute("INSERT INTO book_positions VALUES ('cal:1', ?, ?)", pos)
    return c


class Excerpt(unittest.TestCase):
    def setUp(self):
        B = {"text": TEXT, "total": len(TEXT)}
        patches = [mock.patch.object(excerpt.ebooks, "book_file", return_value=("/x.epub", "EPUB")),
                   mock.patch.object(excerpt.audiomap, "book", return_value=B),
                   mock.patch.object(excerpt.audiomap, "char_of", return_value=TEXT.index("where the reader"))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_starts_at_the_sentence(self):
        t = excerpt.at(conn(pos=("epubcfi(/6/2!/4/2)", 0.1)), "cal:1")
        self.assertTrue(t.startswith("The second one is where the reader stopped"), t)
        self.assertLessEqual(len(t), 300 + 220)
        self.assertTrue(t.endswith(".") or t.endswith("…"), t)

    def test_kindle_percent_without_a_place_in_daf(self):
        t = excerpt.at(conn(progress=50.0), "cal:1")
        self.assertTrue(t)

    def test_never_for_a_private_book(self):
        self.assertIsNone(excerpt.at(conn(private=1, pos=("x", 0.1)), "cal:1"))

    def test_nothing_without_a_place(self):
        self.assertIsNone(excerpt.at(conn(), "cal:1"))

    def test_only_epubs(self):
        with mock.patch.object(excerpt.ebooks, "book_file", return_value=("/x.pdf", "PDF")):
            self.assertIsNone(excerpt.at(conn(pos=("x", 0.1)), "cal:1"))

    def test_a_heading_run_into_the_text_is_left_out(self):
        t = "The last chapter ended here. STRATEGY VERSUS CULTURE In the business world, there is a debate. " + "More words follow on. " * 20
        with mock.patch.object(excerpt.audiomap, "book", return_value={"text": t, "total": len(t)}), \
             mock.patch.object(excerpt.audiomap, "char_of", return_value=t.index("VERSUS")):
            out = excerpt.at(conn(pos=("x", 0.4)), "cal:1")
        self.assertTrue(out.startswith("In the business world"), out)

    def test_a_heading_on_its_own_line_is_left_out(self):
        t = "The end of something.\nStrategy Versus Culture\nIn the business world, there is a debate. " + "More words follow on. " * 20
        with mock.patch.object(excerpt.audiomap, "book", return_value={"text": t, "total": len(t)}), \
             mock.patch.object(excerpt.audiomap, "char_of", return_value=t.index("business")):
            out = excerpt.at(conn(pos=("x", 0.4)), "cal:1")
        self.assertTrue(out.startswith("In the business world"), out)

    def test_a_sentence_beginning_with_I_or_one_capitalised_word_stays(self):
        self.assertEqual(excerpt._drop_heading("I went to the woods. NASA said so."), "I went to the woods. NASA said so.")

    def test_nothing_from_the_copyright_page(self):
        t = "Copyright © 2020 by Someone. All rights reserved. ISBN 978-0-00-000000-0. Cover design by Someone Else. " + "Words. " * 50
        with mock.patch.object(excerpt.audiomap, "book", return_value={"text": t, "total": len(t)}), \
             mock.patch.object(excerpt.audiomap, "char_of", return_value=5):
            self.assertIsNone(excerpt.at(conn(pos=("x", 0.0)), "cal:1"))


if __name__ == "__main__":
    unittest.main()
