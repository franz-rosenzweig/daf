"""What devices may see of private books and items. The Kindle's routes take only the Kindle's token,
and even the Kindle never gets a private book's title back; the phone's widgets and notifications leave
out Feed items with a private title, as /api/tools/feed does."""
import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from fastapi import HTTPException  # noqa: E402

from daf import app, config, db, phone  # noqa: E402

MD5 = "0123456789abcdef0123456789abcdef"
PRIVATE = ["secret diary"]          # stands in for the real list in settings


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        s = config.load_settings() | {"private_titles": PRIVATE}
        self.p = [mock.patch.object(config, "STATE", state), mock.patch.object(config, "DB_PATH", state / "daf.db"),
                  mock.patch.object(config, "load_settings", return_value=s)]
        for p in self.p:
            p.start()
        self.c = db.connect()

    def tearDown(self):
        self.c.close()
        for p in self.p:
            p.stop()
        self.tmp.cleanup()


class Kindle(State):
    def book(self, bid, title, private=0, md5=MD5):
        self.c.execute("INSERT INTO books (id, kind, title, author, private) VALUES (?, 'book', ?, 'Someone', ?)", (bid, title, private))
        self.c.execute("INSERT INTO book_keys (key, book_id) VALUES (?, ?)", ("md5:" + md5, bid))
        self.c.execute("INSERT INTO highlights (id, book_id, source, text, created, seen) VALUES (?, ?, 'epub', 'made in Daf', ?, 1)",
                       ("h-" + bid, bid, int(time.time())))

    def test_only_the_kindles_token(self):
        for name in ("homepage", "desk", "office", "browser", "mac", "phone", "android-sm-x520", "antennapod"):
            with self.assertRaises(HTTPException) as e:
                app.kindle_device(name)
            self.assertEqual(e.exception.status_code, 403)
        self.assertEqual(app.kindle_device("kindle"), "kindle")

    def test_every_kindle_route_asks_for_it(self):
        from fastapi.routing import APIRoute
        dev = [r.path for r in app.app.routes if isinstance(r, APIRoute) and (r.path.startswith("/api/kindle/") or r.path == "/api/sketchbook/kindle/ack")
               and any(d.call is app.device for d in r.dependant.dependencies)]
        self.assertEqual(dev, [], "a Kindle route that any device token opens")

    def test_a_window_cant_make_a_kindle_token(self):
        for name in ("kindle", "kindle-2"):
            req = SimpleNamespace(json=lambda n=name: asyncio.sleep(0, {"name": n}))
            with self.assertRaises(HTTPException) as e:
                asyncio.run(app.make_device(req, self.c))
            self.assertEqual(e.exception.status_code, 400)

    def test_private_book_has_no_title(self):
        self.book("cal:7", "Plain title", private=1)
        got = app.kindle_book(MD5, "kindle", self.c)
        self.assertTrue(got["known"])
        self.assertIsNone(got["title"])
        self.assertEqual([h["id"] for h in got["highlights"]], ["h-cal:7"])    # the Kindle still gets its own book's highlights

    def test_private_by_pattern_has_no_title(self):
        self.book("cal:8", "My Secret Diary, Volume 2")                       # not flagged, but a private title
        self.assertIsNone(app.kindle_book(MD5, "kindle", self.c)["title"])

    def test_other_books_keep_their_title(self):
        self.book("cal:9", "Middlemarch")
        self.assertEqual(app.kindle_book(MD5, "kindle", self.c)["title"], "Middlemarch")


class Phone(State):
    def item(self, did, title, source="Some Blog", feed="f1"):
        self.c.execute("INSERT INTO docs (id, title, source, kind, where_, status, feed, added, thumb) "
                       "VALUES (?, ?, ?, 'article', 'feed', 'unseen', ?, ?, '/api/thumb/t.jpg')",
                       (did, title, source, feed, int(time.time())))

    def fill(self):
        self.item("d1", "Weather today")
        self.item("d2", "Notes from a secret diary")                # a private title
        self.item("d3", "Daily reflection", source="The Secret Diary Blog")  # a private source

    def test_feed_widget(self):
        self.fill()
        got = phone.widget_feed(self.c, config.load_settings(), "")
        self.assertEqual([i["id"] for i in got["items"]], ["d1"])

    def test_spotlight(self):
        self.fill()
        got = phone._spotlight(self.c, config.load_settings(), None)
        self.assertEqual([i["id"] for i in got], ["d1"])

    def test_notifications(self):
        s = config.load_settings() | {"feed_notify": ["f1"]}
        self.fill()
        with mock.patch.object(config, "load_settings", return_value=s):
            got = app.phone_feed_news(0, "phone", self.c)
        self.assertEqual([i["id"] for i in got["items"]], ["d1"])


if __name__ == "__main__":
    unittest.main()
