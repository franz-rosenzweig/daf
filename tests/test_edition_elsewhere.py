"""The Edition's wider taste (daf/elsewhere.py): books, audiobooks, Hardcover, manga, Jellyfin and Seerr, each
with what it's about, private things left out, and the rare piece that names one of them.

Run: .venv/bin/python -m unittest discover tests
"""
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("DAF_STATE", str(HERE / "state-unused"))

from daf import config, db, edition, elsewhere  # noqa: E402

NOW = time.mktime((2026, 3, 18, 4, 0, 0, 0, 0, -1))
DAY = 86400
ISO = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))  # noqa: E731


def fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    return conn


def session(conn, sid, source, item, title, secs, days_ago, private=0, origin="daf-read", author=None):
    conn.execute("INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, private) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (sid, source, origin, item, title, author, int(NOW - days_ago * DAY), secs, private))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        cal = sqlite3.connect(t / "metadata.db")
        cal.executescript("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT); CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);"
                          "CREATE TABLE books_tags_link (book INTEGER, tag INTEGER); CREATE TABLE comments (book INTEGER, text TEXT);"
                          "INSERT INTO books VALUES (5, 'Middlemarch'), (6, 'A Private Book'), (7, 'The Long Shelf');"
                          "INSERT INTO tags VALUES (1, 'Victorian'), (2, 'Marriage'), (3, 'Botany');"
                          "INSERT INTO books_tags_link VALUES (5, 1), (5, 2), (7, 3);"
                          "INSERT INTO comments VALUES (5, '<p>A <b>provincial</b> town &amp; its doctor.</p>'), (7, 'Ferns and mosses.');")
        cal.commit()
        cal.close()
        abs_ = sqlite3.connect(t / "abs.sqlite")
        abs_.executescript("CREATE TABLE books (id TEXT PRIMARY KEY, title TEXT, description TEXT, genres JSON, tags JSON);"
                           "INSERT INTO books VALUES ('ab1', 'Lighthouses', 'Keepers on the coast.', '[\"History\"]', '[\"Maritime\"]');")
        abs_.commit()
        abs_.close()
        self.saved = config.CALIBRE_DBS, config.ABS_DB, elsewhere.TRACK_MAP
        config.CALIBRE_DBS, config.ABS_DB, elsewhere.TRACK_MAP = [t / "metadata.db"], t / "abs.sqlite", str(t / "none.json")
        self.conn = c = fresh_db()
        c.execute("INSERT INTO books (id, kind, title, author, calibre_id, private) VALUES ('cal:5', 'book', 'Middlemarch', 'George Eliot', 5, 0)")
        c.execute("INSERT INTO books (id, kind, title, author, calibre_id, private) VALUES ('cal:6', 'book', 'A Private Book', 'Someone', 6, 1)")
        c.execute("INSERT INTO book_keys (key, book_id) VALUES ('md5:aaa', 'cal:5'), ('md5:ppp', 'cal:6')")
        c.execute("INSERT INTO manga_books (book_id, komga_book, series, series_name) VALUES ('md5:mmm', 'kb1', 'ser1', 'Tide Rider')")

    def tearDown(self):
        config.CALIBRE_DBS, config.ABS_DB, elsewhere.TRACK_MAP = self.saved
        self.conn.close()
        self.tmp.cleanup()


class Books(Fixture):
    def test_a_book_once_with_what_its_about(self):
        session(self.conn, "k1", "kindle", "aaa", "Middlemarch", 3 * 3600, 3, origin="kindle")
        session(self.conn, "d1", "ebook", "cal:5", "Middlemarch", 3600, 1)
        session(self.conn, "k2", "kindle", "ppp", "A Private Book", 5 * 3600, 2, origin="kindle")      # private in Daf
        session(self.conn, "k3", "kindle", "zzz", "Glanced At", 120, 2, origin="kindle")               # a look, not reading
        session(self.conn, "k4", "kindle", "mmm", "Tide Rider", 3600, 2, origin="kindle")              # a manga volume
        got = elsewhere.books(self.conn, NOW, {})
        self.assertEqual([b["title"] for b in got], ["Middlemarch"])
        b = got[0]
        self.assertEqual(b["w"], elsewhere._hours(4 * 3600))                                         # the Kindle's and Daf's hours together
        self.assertIn("Victorian, Marriage", b["text"])
        self.assertIn("A provincial town & its doctor.", b["text"])
        self.assertEqual((b["verb"], b["by"]), ("reading", "George Eliot"))

    def test_private_titles_stay_out(self):
        session(self.conn, "k1", "kindle", "aaa", "Middlemarch", 3 * 3600, 3, origin="kindle")
        self.assertEqual(elsewhere.books(self.conn, NOW, {"private_titles": ["middlemarch"]}), [])

    def test_audiobooks(self):
        session(self.conn, "a1", "audio", "ab1", "Lighthouses (Unabridged)", 7200, 20, origin="audiobookshelf", author="R. Keeper")
        a = elsewhere.audiobooks(self.conn, NOW, {})[0]
        self.assertIn("History, Maritime", a["text"])
        self.assertEqual(a["verb"], "listened to")
        self.assertEqual(elsewhere.short_title(a["title"]), "Lighthouses")

    def test_hardcover_shelves(self):
        shelf = [
            {"book_id": 1, "status_id": 2, "updated_at": ISO(NOW - 5 * DAY), "book": {"title": "The Long Shelf", "cached_contributors": [{"author": {"name": "Ann Fern"}}]}},
            {"book_id": 2, "status_id": 3, "rating": 2.0, "book": {"title": "Not For Me"}},
            {"book_id": 3, "status_id": 1, "privacy_setting_id": 3, "book": {"title": "Hidden"}},
            {"book_id": 4, "status_id": 3, "book": {"title": "Middlemarch"}},          # already counted from the time in it
        ]
        self.conn.execute("INSERT INTO kv (k, v) VALUES ('hardcover', ?)", (json.dumps({"books": shelf}),))
        got = {t["title"]: t for t in elsewhere.shelves(self.conn, NOW, {}, {elsewhere.key("Middlemarch 01 - Middlemarch")})}
        self.assertEqual(set(got), {"The Long Shelf", "Not For Me"})
        self.assertIn("Botany", got["The Long Shelf"]["text"])                    # Calibre's tags, matched by title
        self.assertEqual((got["The Long Shelf"]["w"], got["The Long Shelf"]["verb"]), (0.6, "reading"))
        self.assertLess(got["Not For Me"]["w"], 0)                                   # a low rating says no

    def test_key(self):
        self.assertEqual(elsewhere.key("Tide Rider 03 - The Long Swim"), elsewhere.key("The Long Swim"))
        self.assertEqual(elsewhere.short_title("Small Boats: How a Harbour Learned to Wait"), "Small Boats")


class Screens(unittest.TestCase):
    def setUp(self):
        self.saved = elsewhere._get, elsewhere.secrets.env
        elsewhere.secrets.env = lambda: {"JELLYFIN_API_KEY": "k", "JELLYFIN_USER": "me", "HOMEPAGE_VAR_JELLYSEERR_KEY": "s"}
        played = lambda d: {"LastPlayedDate": ISO(NOW - d * DAY)}  # noqa: E731
        items = {
            "films": [{"Type": "Movie", "Name": "Big Chase", "Genres": ["Action"], "Tags": ["police"], "Overview": "Cops and robbers.", "UserData": played(2)},
                      {"Type": "Movie", "Name": "The Coral Reef", "Genres": ["Documentary"], "Overview": "Reefs are dying.", "UserData": played(3)}],
            "shows": [{"Type": "Episode", "SeriesId": "s1", "SeriesName": "Harbour", "Name": f"Ep {i}", "UserData": played(1 + i)} for i in range(6)],
            "talks": [{"Type": "Video", "Name": "Lecture on Stoics", "UserData": played(4)}],
        }

        def get(url, headers):
            if url.endswith("/Users"):
                return [{"Name": "someone", "Id": "u0"}, {"Name": "me", "Id": "u1"}]
            if url.endswith("/Views"):
                return {"Items": [{"Id": "films", "CollectionType": "movies"}, {"Id": "shows", "CollectionType": "tvshows"},
                                  {"Id": "talks", "CollectionType": "homevideos"}, {"Id": "tunes", "CollectionType": "music"}]}
            if "/Items?" in url:
                lib = url.split("ParentId=")[1].split("&")[0]
                self.assertNotEqual(lib, "tunes")
                return {"Items": items[lib]}
            if url.endswith("/Items/s1"):
                return {"Name": "Harbour", "Genres": ["Drama"], "Tags": ["sea"], "Overview": "A detective in a port town."}
            if "/user?" in url:
                return {"results": [{"id": 1, "jellyfinUsername": "me"}, {"id": 2, "displayName": "Mum"}]}
            if "/request?" in url:
                return {"results": [{"type": "movie", "createdAt": ISO(NOW - 2 * DAY), "requestedBy": {"id": 1}, "media": {"tmdbId": 10}},
                                    {"type": "tv", "createdAt": ISO(NOW - 3 * DAY), "requestedBy": {"id": 2}, "media": {"tmdbId": 11}},
                                    {"type": "movie", "createdAt": ISO(NOW - 4 * DAY), "requestedBy": {"id": 1}, "media": {"tmdbId": 12}}]}
            if url.endswith("/movie/10"):
                return {"title": "Salt Marsh", "genres": [{"name": "Documentary"}], "keywords": [{"name": "wetlands"}], "overview": "Birds."}
            if url.endswith("/movie/12"):
                return {"title": "Space Pirates", "genres": [{"name": "Comedy"}], "keywords": [{"name": "spaceship"}], "overview": "Captain Zog."}
            raise AssertionError(url)
        elsewhere._get = get
        elsewhere._about.clear()

    def tearDown(self):
        elsewhere._get, elsewhere.secrets.env = self.saved

    def test_jellyfin(self):
        got = {t["title"]: t for t in elsewhere.screen(NOW, {})}
        self.assertEqual(set(got), {"Big Chase", "The Coral Reef", "Harbour", "Lecture on Stoics"})
        self.assertLess(got["Big Chase"]["w"], got["The Coral Reef"]["w"])           # fiction lightly
        self.assertNotIn("Cops", got["Big Chase"]["text"])                            # and by its genres and keywords only
        self.assertIn("Reefs are dying", got["The Coral Reef"]["text"])
        self.assertEqual(got["Lecture on Stoics"]["w"], 1.2)                         # a home video is a lecture
        self.assertEqual((got["Harbour"]["w"], got["Harbour"]["verb"]), (0.6, "watching"))   # six episodes, one show
        self.assertIn("sea", got["Harbour"]["text"])

    def test_seerr_mine_only(self):
        got = {t["title"]: t for t in elsewhere.requested(NOW, {})}
        self.assertEqual(set(got), {"Salt Marsh", "Space Pirates"})                 # not Mum's
        self.assertEqual((got["Salt Marsh"]["w"], got["Space Pirates"]["w"]), (1.0, 0.35))
        self.assertNotIn("Zog", got["Space Pirates"]["text"])

    def test_asked_once_then_kept(self):
        calls = []
        saved = elsewhere.screen, elsewhere.requested
        elsewhere.screen = lambda now, s: calls.append("j") or [{"kind": "screen", "title": "X", "when": NOW, "w": 1, "text": "x", "verb": "watched"}]
        elsewhere.requested = lambda now, s: calls.append("s") or (_ for _ in ()).throw(OSError("down"))
        elsewhere._remote.update(at=0.0, data=None)
        try:
            self.assertEqual(len(elsewhere._from_servers({})), 1)
            elsewhere._from_servers({})
            self.assertEqual(calls, ["j", "s"])                                       # kept, and Seerr's failure didn't lose Jellyfin's
            self.assertLess(elsewhere._remote["at"] - time.time(), elsewhere.RETRY + 5)   # asked again sooner after a failure
        finally:
            elsewhere.screen, elsewhere.requested = saved
            elsewhere._remote.update(at=0.0, data=None)


class GoesWith(unittest.TestCase):
    THINGS = [
        {"kind": "screen", "title": "Harbour", "when": NOW - DAY, "w": 0.6, "text": "Harbour Drama sea", "verb": "watching"},
        {"kind": "book", "title": "Middlemarch 01 - Middlemarch", "when": NOW - 2 * DAY, "w": 1.5, "text": "Middlemarch George Eliot Victorian marriage",
         "verb": "reading", "by": "George Eliot"},
        {"kind": "book", "title": "Old Want", "when": NOW - 2 * DAY, "w": 0.2, "text": "Old Want", "verb": "want to read", "shelf": True},
        {"kind": "book", "title": "Long Ago", "when": NOW - 200 * DAY, "w": 1.5, "text": "Long Ago", "verb": "read"},
    ]

    def test_lately(self):
        got = elsewhere.lately(self.THINGS, NOW)
        self.assertEqual([t["title"] for t in got], ["Middlemarch", "Harbour"])       # not a want-to-read, not last year's
        self.assertEqual(got[0]["names"], ["Middlemarch", "Middlemarch 01 - Middlemarch", "George Eliot"])

    def test_a_piece_has_to_name_it(self):
        lat = elsewhere.lately(self.THINGS, NOW)
        cands = [{"title": "What George Eliot knew about doctors", "summary": ""},
                 {"title": "A harbour at dawn", "summary": "Boats in the harbour."},          # lower case: just a harbour
                 {"title": "The sea and marriage in Victorian novels", "summary": ""}]       # the words, not the book
        ms = elsewhere.matchers(lat, cands)
        self.assertEqual([(elsewhere.near(c, ms) or {}).get("title") for c in cands], ["Middlemarch", None, None])
        self.assertEqual(elsewhere.near_line(elsewhere.near(cands[0], ms)), "Goes with Middlemarch, which you're reading")

    def test_a_name_everyone_uses_doesnt_count(self):
        lat = elsewhere.lately(self.THINGS, NOW)
        cands = [{"title": f"Harbour news {i}", "summary": ""} for i in range(elsewhere.COMMON)]
        self.assertFalse([t for t, _ in elsewhere.matchers(lat, cands) if t["title"] == "Harbour"])


class InTheTaste(Fixture):
    def test_taste_and_the_why(self):
        e = dict(edition.DEFAULTS, desks=[])
        iv = {"hist": [], "watched": set(), "rate": 10, "playlists": [], "lanes": [], "named": [], "suggest": False}
        prof = edition.taste(self.conn, e, NOW, iv, more=GoesWith.THINGS)
        self.assertEqual((prof["seen"].get("book"), prof["seen"].get("screen")), (3, 1))
        self.assertGreater(prof["words"].get("victorian", 0), 0)
        self.assertEqual([t["title"] for t in prof["lately"]], ["Middlemarch", "Harbour"])
        c = {"id": "x", "kind": "article", "title": "Middlemarch at 150", "summary": "", "source": "Aeon", "published": NOW, "origin": "feed"}
        got = edition.score([c], prof, e, NOW)[0]
        self.assertEqual(got["near"], {"title": "Middlemarch", "verb": "reading"})
        self.assertEqual(edition.fact_line(got), "Goes with Middlemarch, which you're reading")
        self.assertIn("goes with Middlemarch", edition._facts_text(got, None))
        self.assertIn("Middlemarch (book, reading)", edition._taste_text(prof))


if __name__ == "__main__":
    unittest.main()
