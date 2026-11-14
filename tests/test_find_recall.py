"""Find details' second try and its "surely the same book" test (calibrefind.same_book, main_title, find)."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import calibrefind as c  # noqa: E402


class SameBook(unittest.TestCase):
    def test_authors(self):
        book = {"title": "A Made Up Essay Collection: On Things", "authors": ["Second Writer", "Ana Vilf"]}
        self.assertTrue(c.same_book(book, {"title": "A Made Up Essay Collection", "authors": ["Ana Wilf"]}))       # a letter apart, either author
        self.assertTrue(c.same_book(book, {"title": "A Made Up Essay Collection", "authors": ["Second Writer"]}))
        self.assertFalse(c.same_book(book, {"title": "A Made Up Essay Collection", "authors": ["Someone Else"]}))
        self.assertTrue(c.same_book({"title": "ספר בדוי", "authors": ["פלוני אלמוני"]}, {"title": "ספר בדוי", "authors": ["פלוני אלמוני"]}))

    def test_titles(self):
        a = {"title": "The Long Made Up Title Without Its Colon Here", "authors": ["Some One"]}
        self.assertTrue(c.same_book(a, {"title": "The Long Made Up Title: Without Its Colon Here", "authors": ["Some One"]}))
        self.assertFalse(c.same_book({"title": "Sand", "authors": ["Some One"]}, {"title": "Sand Worms", "authors": ["Some One"]}))
        self.assertTrue(c.same_book({"title": "Sand", "authors": ["Some One"]}, {"title": "Sand: A Novel", "authors": ["Some One"]}))

    def test_main_title(self):
        self.assertEqual(c.main_title("Three Word Title: And Its Subtitle"), "Three Word Title")
        self.assertEqual(c.main_title("Short: A Memoir"), "Short: A Memoir")             # one word left: the whole title


class SecondTry(unittest.TestCase):
    def test_title_alone_when_nothing(self):
        calls = []

        def src(title, authors, ids, timeout=30, plugins=None, info=None):
            calls.append((title, tuple(authors), bool(ids)))
            return [] if authors else [{"title": "Three Word Title", "authors": ["Ana Wilf"], "identifiers": {}, "source": "Goodreads"}]
        with mock.patch.object(c, "calibre_sources", side_effect=src), mock.patch.object(c, "hardcover", return_value=[]):
            r = c.find(lambda: mock.MagicMock(), 1, "cal:1", "Three Word Title: And Its Subtitle", ["Ana Vilf"], {})
        self.assertEqual([x["title"] for x in r["results"]], ["Three Word Title"])
        self.assertEqual(calls[-1], ("Three Word Title", (), False))


if __name__ == "__main__":
    unittest.main()
