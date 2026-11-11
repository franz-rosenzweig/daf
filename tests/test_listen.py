"""Listen's new tools, against made-up shows and a stand-in Audiobookshelf (tools/fake_abs.py):
- Download: a show's choice (off, new, all) asks for the right episodes; one episode kept and let go;
  the file comes whole, or not at all when the disk is nearly full; the player then plays Daf's copy.
- Mark all played: every episode not played gets a play to its end, with no listening time.
- The Audiobooks page: series, authors, narrators and collections; an audiobook's page with its chapters,
  bookmarks, files, collections and week; bookmarks, collections, Finished and Find details / Use, each
  a write to the stand-in only.
- The routes turn away what isn't an address or an item.

Run: .venv/bin/python -m unittest discover -s tests
"""
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "tools"))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))   # importing daf never touches the real state

from fastapi import HTTPException  # noqa: E402

from daf import absapi, config, db, downloads, episodes, podcasts  # noqa: E402
import fake_abs  # noqa: E402

FEED = "https://example.org/feed.xml"
AUDIO = b"ID3" + b"\0" * 40000


class Files(BaseHTTPRequestHandler):
    """An episode's host: /ep<n>.mp3 is a small file, /empty.mp3 is nothing."""
    def log_message(self, *a):
        pass

    def do_GET(self):
        data = b"" if self.path.startswith("/empty") else AUDIO
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = (config.STATE, config.DB_PATH)
        config.STATE = Path(self.tmp.name)
        config.DB_PATH = config.STATE / "daf.db"
        self.conn = db.connect()

    def tearDown(self):
        self.conn.close()
        config.STATE, config.DB_PATH = self._old
        self.tmp.cleanup()

    def episodes(self, base, n=4, day=86400):
        """n episodes of the show, one a day, the newest yesterday."""
        import time
        now = int(time.time())
        self.conn.execute("INSERT INTO gp_subs (url, title, added) VALUES (?, 'A show', ?)", (FEED, now))
        urls = []
        for i in range(n):
            u = f"{base}/ep{i}.mp3"
            self.conn.execute("INSERT INTO gp_episodes (url, title, podcast, podcast_title, published, duration) VALUES (?, ?, ?, 'A show', ?, 600)",
                              (u, f"Episode {i}", FEED, now - (n - i) * day))
            urls.append(u)
        return urls


class Downloads(State):
    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Files)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self._free, downloads.MIN_FREE = downloads.MIN_FREE, 0          # a test's folder is small, and in memory

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        downloads.MIN_FREE = self._free
        super().tearDown()

    def queued(self):
        return {r[0] for r in self.conn.execute("SELECT ref FROM jobs WHERE kind = 'epdl' AND status = 'queued'")}

    def test_show_choice(self):
        urls = self.episodes(self.base)
        self.assertEqual(downloads.mode(self.conn, FEED)["mode"], "off")
        self.assertEqual(downloads.set_mode(self.conn, FEED, "new")["queued"], 0)      # nothing has come out since
        self.conn.execute("UPDATE gp_episodes SET published = published + 86400 + 60 WHERE url = ?", (urls[-1],))
        self.assertEqual(downloads.plan(self.conn), 1)                                 # the next day's reading finds one
        self.assertEqual(self.queued(), {urls[-1]})
        self.assertEqual(downloads.set_mode(self.conn, FEED, "all")["queued"], 3)
        self.assertEqual(self.queued(), set(urls))
        downloads.set_mode(self.conn, FEED, "off")                                     # off: what's waiting goes
        self.assertEqual(self.queued(), set())
        self.assertEqual(downloads.states(self.conn), {})
        with self.assertRaises(ValueError):
            downloads.set_mode(self.conn, FEED, "some")

    def test_keep_play_and_let_go(self):
        urls = self.episodes(self.base)
        self.assertEqual(downloads.want(self.conn, urls[0]), "queued")
        self.conn.commit()
        downloads.fetch(urls[0])
        k = downloads.kept(self.conn, urls[0])
        self.assertIsNotNone(k)
        self.assertEqual(k[0].read_bytes(), AUDIO)
        self.assertEqual(downloads.want(self.conn, urls[0]), "done")                   # asked again: it's there
        # the episode plays from Daf's copy, and the list knows it's downloaded
        st = episodes.state(self.conn, {"enclosure": urls[0], "where_": "podcast"}, opening=False)
        self.assertTrue(st["audio"].startswith("/api/podcasts/kept?u="))
        self.assertTrue(st["kept"])
        got = podcasts.episode_list(self.conn, FEED, "downloaded")
        self.assertEqual([e["audio"] for e in got["episodes"]], [urls[0]])
        self.assertEqual(podcasts.show(self.conn, FEED, read=False)["episodes"][-1]["kept"], "done")
        downloads.drop(self.conn, urls[0])
        self.assertFalse(k[0].exists())
        self.assertIsNone(downloads.kept(self.conn, urls[0]))

    def test_not_when_the_disk_is_full_or_the_file_empty(self):
        urls = self.episodes(self.base, 1)
        downloads.want(self.conn, urls[0])
        self.conn.commit()
        downloads.MIN_FREE = 1 << 62
        with self.assertRaises(RuntimeError):
            downloads.fetch(urls[0])
        downloads.MIN_FREE = 0
        self.assertEqual(downloads.states(self.conn), {urls[0]: "failed"})
        empty = self.base + "/empty.mp3"
        self.conn.execute("INSERT INTO gp_episodes (url, title, podcast) VALUES (?, 'Empty', ?)", (empty, FEED))
        downloads.want(self.conn, empty)
        self.conn.commit()
        with self.assertRaises(RuntimeError):
            downloads.fetch(empty)
        self.assertEqual(list(downloads.folder().iterdir()), [])                       # no half file left behind

    def test_mark_all_played(self):
        urls = self.episodes(self.base, 3)
        self.conn.execute("INSERT INTO gp_actions (podcast, episode, action, position, started, total, timestamp, device) "
                          "VALUES (?, ?, 'play', 600, 0, 600, 1, 'antennapod')", (FEED, urls[0]))
        sessions = self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        self.assertEqual(podcasts.mark_played(self.conn, FEED), {"marked": 2})
        self.assertEqual(podcasts.episode_list(self.conn, FEED, "unplayed")["total"], 0)
        self.assertEqual(podcasts.episode_list(self.conn, FEED, "played")["total"], 3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], sessions)   # no listening time
        self.assertEqual(podcasts.mark_played(self.conn, FEED), {"marked": 0})


class Audiobooks(State):
    @classmethod
    def setUpClass(cls):
        from daf import secrets
        cls.srv, cls.fake, base = fake_abs.serve()
        cls._abs = (config.ABS_URL, secrets.abs_key)
        config.ABS_URL = base
        secrets.abs_key = lambda: "fake"

    @classmethod
    def tearDownClass(cls):
        from daf import secrets
        cls.srv.shutdown()
        cls.srv.server_close()
        config.ABS_URL, secrets.abs_key = cls._abs

    def setUp(self):
        super().setUp()
        absapi.forget()

    def test_shelf_groups(self):
        books = {b["item"]: b for b in absapi.audiobooks(self.conn)}
        self.assertEqual(books["scarlet"]["series"], [{"name": "Sherlock Holmes", "seq": "1"}])
        self.assertEqual(books["moby"]["narrators"], ["Tom Weiss"])
        self.assertEqual(books["pride"]["authors"], ["Jane Austen"])
        cols = {c["name"]: c["books"] for c in absapi.collections()}
        self.assertEqual(cols["Car rides"], ["scarlet", "adventures"])
        self.assertEqual(absapi.series_of("A #1, B Two #2.5, Lone"), [{"name": "A", "seq": "1"}, {"name": "B Two", "seq": "2.5"}, {"name": "Lone", "seq": ""}])

    def test_book_page(self):
        p = absapi.book_page(self.conn, "moby")
        self.assertEqual(p["title"], "Moby-Dick")
        self.assertEqual(p["chapters"][0]["title"], "Loomings")
        self.assertEqual([b["title"] for b in p["bookmarks"]], ["Queequeg at the inn", "Father Mapple’s sermon", ""])
        self.assertEqual(len(p["files"]), 3)
        self.assertEqual({c["name"]: c["on"] for c in p["collections"]}, {"Long winter": True, "Car rides": False})
        self.assertEqual(len(p["week"]), 7)
        self.assertEqual(p["week"][-1]["secs"], 62 * 60)
        self.assertEqual(sum(d["secs"] for d in p["week"]), (40 + 22 + 55 + 10 + 62) * 60)
        with self.assertRaises(KeyError):
            absapi.book_page(self.conn, "lv-poetry")                # a recording isn't an audiobook

    def test_bookmarks(self):
        n = len(self.fake.writes)
        absapi.bookmark_add("scarlet", 125.6, "The doctor")
        self.assertEqual([(b["t"], b["title"]) for b in absapi.book_page_marks("scarlet")], [(125, "The doctor")])
        absapi.bookmark_edit("scarlet", 125, "Watson")
        self.assertEqual(absapi.book_page_marks("scarlet")[0]["title"], "Watson")
        absapi.bookmark_drop("scarlet", 125)
        self.assertEqual(absapi.book_page_marks("scarlet"), [])
        self.assertEqual([w[0] for w in self.fake.writes[n:]], ["POST", "PATCH", "DELETE"])

    def test_collections_and_finished(self):
        absapi.collection_set("four", "col-car", True)
        self.assertIn("four", next(c for c in absapi.collections() if c["id"] == "col-car")["books"])
        absapi.collection_set("four", "col-car", False)
        self.assertNotIn("four", next(c for c in absapi.collections() if c["id"] == "col-car")["books"])
        made = absapi.collection_new("dracula", "Autumn")
        self.assertEqual(made["name"], "Autumn")
        self.assertEqual(next(c for c in absapi.collections() if c["name"] == "Autumn")["books"], ["dracula"])
        absapi.finished("dracula", True)
        self.assertTrue(absapi.where("dracula")["isFinished"])

    def test_find_and_use_details(self):
        self.assertIn("audible", [p["value"] for p in absapi.providers()])
        found = absapi.find_details("frankenstein", "google")
        self.assertEqual(found[0]["title"], "Frankenstein")
        self.assertEqual(found[0]["year"], "1851")
        cand = dict(found[1], narrator="Elena Marsh, Tom Weiss")
        used = absapi.use_details("frankenstein", cand)
        self.assertIn("publishedYear", used)
        md = absapi.item("frankenstein")["media"]["metadata"]
        self.assertEqual(md["title"], "Frankenstein (Unabridged)")
        self.assertEqual(md["narrators"], ["Elena Marsh", "Tom Weiss"])
        self.assertEqual(md["publishedYear"], "2003")
        with self.assertRaises(ValueError):
            absapi.use_details("frankenstein", {"title": "  "})


class Routes(State):
    def test_turned_away(self):
        from daf import app
        with self.assertRaises(HTTPException) as e:
            app.post_podcasts_download({"feed": "file:///etc/passwd", "mode": "all"}, self.conn)
        self.assertEqual(e.exception.status_code, 400)
        with self.assertRaises(HTTPException) as e:
            app.post_podcasts_download({"feed": FEED, "mode": "every"}, self.conn)
        self.assertEqual(e.exception.status_code, 400)
        with self.assertRaises(HTTPException) as e:
            app.post_podcasts_keep({"audio": "https://example.org/not-known.mp3"}, self.conn)
        self.assertEqual(e.exception.status_code, 404)
        with self.assertRaises(HTTPException) as e:
            app.get_podcasts_kept("https://example.org/not-known.mp3", self.conn)
        self.assertEqual(e.exception.status_code, 404)
        with self.assertRaises(HTTPException) as e:
            app.post_podcasts_played({"feed": "nope"}, self.conn)
        self.assertEqual(e.exception.status_code, 400)
        with self.assertRaises(HTTPException) as e:
            app.post_abs_bookmark("../me", {"t": 1})
        self.assertEqual(e.exception.status_code, 400)
        with self.assertRaises(HTTPException) as e:
            app.get_abs_find("moby", provider="a/b")
        self.assertEqual(e.exception.status_code, 400)
        self.assertEqual(app.post_podcasts_download({"feed": FEED, "mode": "all"}, self.conn), {"mode": "all", "queued": 0})


if __name__ == "__main__":
    unittest.main()
