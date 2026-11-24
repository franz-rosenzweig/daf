"""The Kindle and the audiobook (audiomap.kindle_offer, audiomap.reading_place): when a book opens on the
Kindle, the audiobook's place is offered there if it was played after the Kindle's last page; while Daf
hears it the answer is "pending" and the plugin asks again; and Listen from here starts from the newer
of Daf's place and the Kindle's, with the Kindle's page's words when it sent them.

Audiobookshelf and the hearing are stood in for: absapi.for_book / playable and audiomap.to_book.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).parent
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from daf import absapi, app, audiomap, config, db, soundscape  # noqa: E402

MD5 = "0123456789abcdef0123456789abcdef"
NOW = int(time.time())


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        state = Path(self.tmp.name)
        self.p = [mock.patch.object(config, "STATE", state), mock.patch.object(config, "DB_PATH", state / "daf.db")]
        for p in self.p:
            p.start()
        self.c = db.connect()
        self.c.execute("INSERT INTO books (id, kind, title, author) VALUES ('cal:1', 'book', 'A Book', 'Someone')")
        self.c.execute("INSERT INTO book_keys (key, book_id) VALUES (?, 'cal:1')", ("md5:" + MD5,))
        self.c.commit()
        audiomap._offers.clear()

    def tearDown(self):
        self.c.close()
        for p in self.p:
            p.stop()
        self.tmp.cleanup()


class Offer(State):
    def setUp(self):
        super().setUp()
        self.item = "abs-1"
        self.played = {"at": 3600.0, "done": False, "last": NOW - 600}
        self.asked = []
        self.place = {"words": "the words at that second", "fraction": 0.42, "chapter": "Chapter 4", "how": "map"}
        self.exact = {"words": "the words heard there", "fraction": 0.43, "chapter": "Chapter 4", "how": "words"}

        def to_book(conn, book_id, t, exact=False):
            self.asked.append((book_id, t, exact))
            return dict(self.exact if exact else self.place) if self.place is not None else None
        self.q = [mock.patch.object(absapi, "for_book", lambda conn, bid: self.item if bid == "cal:1" else None),
                  mock.patch.object(absapi, "playable", lambda item: dict(self.played)),
                  mock.patch.object(audiomap, "to_book", to_book)]
        for q in self.q:
            q.start()

    def tearDown(self):
        for q in self.q:
            q.stop()
        super().tearDown()

    def ask(self, since=0):
        return app.kindle_audio(md5=MD5, since=since, name="kindle", c=self.c)

    def wait(self, since=0):
        for _ in range(200):
            r = self.ask(since)
            if not r.get("pending"):
                return r
            time.sleep(0.02)
        self.fail("still pending")

    def test_the_book_says_it_has_an_audiobook(self):
        self.assertTrue(app.kindle_book(md5=MD5, name="kindle", c=self.c)["audio"])
        self.item = None
        self.assertFalse(app.kindle_book(md5=MD5, name="kindle", c=self.c)["audio"])

    def test_heard_on_its_own_thread_then_offered(self):
        self.assertEqual(self.ask(), {"pending": True})
        r = self.wait()
        self.assertEqual(r["offer"]["words"], "the words heard there")
        self.assertEqual((r["offer"]["at"], r["offer"]["last"]), (3600.0, NOW - 600))
        self.assertEqual([a for a in self.asked if a[2]], [("cal:1", 3600, True)])     # heard once
        self.assertEqual(self.ask(), r)                                                 # and kept

    def test_a_prepared_audiobook_answers_at_once(self):
        self.place = dict(self.exact)                     # readalong's points: "words" without hearing
        r = self.ask()
        self.assertEqual(r["offer"]["fraction"], 0.43)
        self.assertFalse([a for a in self.asked if a[2]])

    def test_nothing_when_the_kindle_is_newer(self):
        self.assertEqual(self.ask(since=NOW - 60), {})
        self.assertEqual(self.asked, [])

    def test_nothing_when_finished_or_barely_started(self):
        self.played["done"] = True
        self.assertEqual(self.ask(), {})
        self.played.update(done=False, at=12.0)
        self.assertEqual(self.ask(), {})

    def test_nothing_when_it_isnt_found(self):
        self.place = None                                 # no EPUB to find it in
        self.assertEqual(self.ask(), {})

    def test_hearing_that_fails_offers_nothing(self):
        def broken(conn, book_id, t, exact=False):
            if exact:
                raise RuntimeError("whisper went away")
            return dict(self.place)
        with mock.patch.object(audiomap, "to_book", broken), self.assertLogs("daf.audiomap", "ERROR"):
            self.assertEqual(self.ask(), {"pending": True})
            self.assertEqual(self.wait(), {})

    def test_abs_away_is_no_offer(self):
        def away(item):
            raise absapi.Unavailable("Audiobookshelf didn't answer")
        with mock.patch.object(absapi, "playable", away):
            self.assertEqual(self.ask(), {})

    def test_an_unknown_book(self):
        self.assertEqual(app.kindle_audio(md5="f" * 32, since=0, name="kindle", c=self.c), {})


class Reading(State):
    def daf(self, fraction, at):
        self.c.execute("INSERT OR REPLACE INTO book_positions (book_id, cfi, fraction, chapter, updated) VALUES ('cal:1', 'epubcfi(/6/8!/4/2)', ?, 'Two', ?)",
                       (fraction, at))

    def kindle(self, page, total, at):
        self.c.execute("INSERT INTO pages (md5, start, duration, page, total, origin) VALUES (?, ?, 30, ?, ?, 'daf')", (MD5, at, page, total))

    def test_none_yet(self):
        self.assertIsNone(audiomap.reading_place(self.c, "cal:1"))

    def test_dafs_own_place(self):
        self.daf(0.2, NOW - 100)
        r = audiomap.reading_place(self.c, "cal:1")
        self.assertEqual((r["where"], r["cfi"], r["fraction"]), ("daf", "epubcfi(/6/8!/4/2)", 0.2))

    def test_the_kindle_when_its_newer(self):
        self.daf(0.2, NOW - 3600)
        self.kindle(150, 300, NOW - 100)
        r = audiomap.reading_place(self.c, "cal:1")
        self.assertEqual((r["where"], r["fraction"], r.get("text")), ("kindle", 0.5, None))

    def test_daf_when_its_newer(self):
        self.kindle(150, 300, NOW - 3600)
        self.daf(0.2, NOW - 100)
        self.assertEqual(audiomap.reading_place(self.c, "cal:1")["where"], "daf")

    def test_the_kindles_page_words(self):
        self.kindle(150, 300, NOW - 100)
        soundscape.kindle_where(self.c, "cal:1", "and so the words on the Kindle's page", 0.51)
        r = audiomap.reading_place(self.c, "cal:1")
        self.assertEqual((r["where"], r["text"], r["fraction"]), ("kindle", "and so the words on the Kindle's page", 0.51))
        self.assertEqual(json.loads(self.c.execute("SELECT v FROM kv WHERE k = 'kindle_where'").fetchone()[0])["book_id"], "cal:1")   # Sound's, as before

    def test_words_from_an_older_page_are_left(self):
        soundscape.kindle_where(self.c, "cal:1", "a page from long ago", 0.1)
        self.c.execute("UPDATE kv SET v = json_set(v, '$.at', ?) WHERE k = 'kindle_page:cal:1'", (NOW - 7200,))
        self.kindle(150, 300, NOW - 100)                  # read on after it, with no words sent
        r = audiomap.reading_place(self.c, "cal:1")
        self.assertEqual((r["fraction"], r.get("text")), (0.5, None))

    def test_listen_from_here_starts_at_the_kindles_page(self):
        self.daf(0.2, NOW - 3600)
        self.kindle(150, 300, NOW - 100)
        soundscape.kindle_where(self.c, "cal:1", "and so the words on the Kindle's page", 0.51)
        got = []
        with mock.patch.object(audiomap, "from_book", lambda conn, bid, place, exact=False: got.append(place) or {"t": 1.0, "chapter": None, "how": "map"}):
            app.post_abs_book_start("cal:1", {}, self.c)
            app.post_abs_book_start("cal:1", {"cfi": "epubcfi(/6/2)", "fraction": 0.1}, self.c)     # the reader's own page still wins
        self.assertEqual(got, [{"fraction": 0.51, "text": "and so the words on the Kindle's page"}, {"cfi": "epubcfi(/6/2)", "fraction": 0.1}])

    def test_no_place_at_all(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as e:
            app.post_abs_book_start("cal:1", {}, self.c)
        self.assertEqual(e.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
