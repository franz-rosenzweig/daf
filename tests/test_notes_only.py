"""The Notebook by itself (book.js's #ebook/<id>/notes): while it asks (POST /api/sketchbook/follow/<id>)
the book counts as followed for ten minutes (sketchbook.following), the Kindle is told so (the book's
answer, /api/kindle/follow, and the answer to each page it sends), and the ask says where I'm reading it."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from fastapi.routing import APIRoute  # noqa: E402

from daf import absapi, app, config, db, sketchbook, soundscape  # noqa: E402

MD5 = "0123456789abcdef0123456789abcdef"
NOW = int(time.time())


def route(path, method):
    for r in app.app.routes:
        if isinstance(r, APIRoute) and r.path == path and method in r.methods:
            return r.endpoint
    raise LookupError(path)


class Notes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.p = [mock.patch.object(config, "STATE", state), mock.patch.object(config, "DB_PATH", state / "daf.db"),
                  mock.patch.object(absapi, "for_book", lambda conn, bid: None)]
        for p in self.p:
            p.start()
        self.c = db.connect()
        self.c.execute("INSERT INTO books (id, kind, title, author) VALUES ('cal:1', 'book', 'A Book', 'Someone')")
        self.c.execute("INSERT INTO book_keys (key, book_id) VALUES (?, 'cal:1')", ("md5:" + MD5,))
        self.c.commit()
        self.follow = route("/api/sketchbook/follow/{book_id}", "POST")
        self.where = route("/api/kindle/where", "POST")

    def tearDown(self):
        self.c.close()
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_not_followed_until_asked(self):
        self.assertFalse(sketchbook.following(self.c, "cal:1"))
        self.assertFalse(app.kindle_book(md5=MD5, name="kindle", c=self.c)["follow"])
        self.assertEqual(app.kindle_follow(md5=MD5, name="kindle", c=self.c), {"follow": False})

    def test_asking_makes_it_followed(self):
        self.follow("cal:1", self.c)
        self.assertTrue(sketchbook.following(self.c, "cal:1"))
        self.assertTrue(app.kindle_book(md5=MD5, name="kindle", c=self.c)["follow"])
        self.assertEqual(app.kindle_follow(md5=MD5, name="kindle", c=self.c), {"follow": True})
        self.assertFalse(sketchbook.following(self.c, "cal:2"))          # only that book

    def test_ten_minutes_after_the_last_ask_it_stops(self):
        self.follow("cal:1", self.c)
        self.c.execute("UPDATE kv SET v = ? WHERE k = 'notes_open:cal:1'", (str(NOW - sketchbook.FOLLOW - 5),))
        self.assertFalse(sketchbook.following(self.c, "cal:1"))
        self.assertFalse(app.kindle_follow(md5=MD5, name="kindle", c=self.c)["follow"])

    def test_each_page_sent_hears_whether_to_go_on(self):
        self.assertEqual(self.where({"md5": MD5, "text": "a page", "fraction": 0.2}, "kindle", self.c), {"ok": True, "follow": False})
        self.follow("cal:1", self.c)
        self.assertEqual(self.where({"md5": MD5, "text": "the next page", "fraction": 0.21}, "kindle", self.c), {"ok": True, "follow": True})

    def test_the_ask_says_where_im_reading(self):
        self.assertEqual(self.follow("cal:1", self.c), {"place": None})
        self.c.execute("INSERT INTO pages (md5, start, duration, page, total, origin) VALUES (?, ?, 30, 120, 300, 'daf')", (MD5, NOW - 60))
        soundscape.kindle_where(self.c, "cal:1", "the words on the Kindle's page", 0.4)
        p = self.follow("cal:1", self.c)["place"]
        self.assertEqual((p["where"], p["text"], p["fraction"]), ("kindle", "the words on the Kindle's page", 0.4))
        # read on in Daf (on another device) after that: the Notebook follows Daf's place
        self.c.execute("INSERT INTO book_positions (book_id, cfi, fraction, chapter, updated) VALUES ('cal:1', 'epubcfi(/6/10!/4/2)', 0.45, 'Five', ?)",
                       (int(time.time()) + 5,))
        p = self.follow("cal:1", self.c)["place"]
        self.assertEqual((p["where"], p["cfi"]), ("daf", "epubcfi(/6/10!/4/2)"))

    def test_a_bad_book_id(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            self.follow("cal:1/../x y", self.c)

    def test_the_kv_is_a_time(self):
        self.follow("cal:1", self.c)
        v = self.c.execute("SELECT v FROM kv WHERE k = 'notes_open:cal:1'").fetchone()[0]
        self.assertLessEqual(abs(int(v) - time.time()), 5)
        self.assertEqual(json.loads(v), int(v))


if __name__ == "__main__":
    unittest.main()
