"""The phone's home-screen widgets (daf/phone.py widgets, widget_feed): a private book is never named
or shown, a book opens where it can be read, and a Feed widget asks for its own part of the Feed.

Run: .venv/bin/python -m unittest discover tests
"""
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import phone, reader  # noqa: E402


class Books(unittest.TestCase):
    def test_private_book_unnamed(self):
        b = phone._book({"id": "cal:9", "title": "A Secret: With a Subtitle", "author": "Someone", "private": 1,
                          "calibre_path": "/x", "progress": 12.0}, {"cal:9"})
        self.assertEqual(b["title"], "A private book")
        self.assertEqual(b["author"], "")
        self.assertIsNone(b["cover"])
        self.assertEqual(b["progress"], 12.0)

    def test_route_and_cover(self):
        r = {"id": "cal:4", "title": "Gilead: A Novel", "author": "Marilynne Robinson", "calibre_path": "/books/g", "progress": 40.0}
        readable = phone._book(r, {"cal:4"})
        self.assertEqual(readable["title"], "Gilead")
        self.assertEqual(readable["route"], "#ebook/cal:4")
        self.assertEqual(readable["cover"], "/api/cover/cal:4")
        self.assertEqual(phone._book(r, set())["route"], "#book/cal:4")      # no file Daf can open: its page
        self.assertIsNone(phone._book(dict(r, calibre_path=None), set())["cover"])


class Feed(unittest.TestCase):
    def setUp(self):
        self.asked = []
        self.real = reader.list_docs

        def list_docs(conn, settings, where, tab, kind, cat, limit, offset, sort, feed, flt, q):
            self.asked.append((where, tab, cat, feed, limit))
            return [{"id": "rss:1", "title": "A post", "source": "A blog", "published": 100, "thumb": None, "kind": "article"}]
        reader.list_docs = list_docs

    def tearDown(self):
        reader.list_docs = self.real

    def test_sources(self):
        phone.widget_feed(None, {}, "", 5)
        phone.widget_feed(None, {}, "folder:Craft", 5)
        out = phone.widget_feed(None, {}, "feed:feed/34", 500)
        self.assertEqual(self.asked, [("feed", "unseen", None, None, 5), ("feed", "unseen", "Craft", None, 5),
                                      ("feed", "unseen", None, "feed/34", 40)])
        self.assertEqual(out["items"][0]["route"], "#read/rss:1")


if __name__ == "__main__":
    unittest.main()
