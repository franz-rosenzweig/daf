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


if __name__ == "__main__":
    unittest.main()
