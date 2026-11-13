"""Recents (daf/recents.py), on a made-up day of sittings and opens."""
import sqlite3
import unittest
from datetime import datetime, time
from zoneinfo import ZoneInfo

from daf import db, recents

TZ = "America/Phoenix"
SETTINGS = {"home_tz": TZ}


def at(day, hh, mm):
    return int(datetime.combine(datetime.fromisoformat(day).date(), time(hh, mm), ZoneInfo(TZ)).timestamp())


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(db.SCHEMA)
    for table, col, decl in db.MIGRATIONS:
        if col not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    d = "2026-03-04"
    c.execute("INSERT INTO books (id, kind, title, author, calibre_path) VALUES ('cal:1', 'book', 'A Field Guide', 'A. Writer', 'A/B')")
    c.execute("INSERT INTO book_keys (key, book_id) VALUES ('md5:abc', 'cal:1')")
    c.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, opened) VALUES "
              "('kk:1', 'article', 'library', 'inbox', 'How to Begin', 'A Blog', 'https://example.org/begin', ?)", (at(d, 21, 0),))
    c.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, opened) VALUES "
              "('rss:1', 'article', 'feed', 'inbox', 'How to Begin', 'A Blog', 'https://example.org/begin', ?)", (at(d, 20, 59),))
    c.execute("INSERT INTO docs (id, kind, where_, status, title, source, url, opened) VALUES "
              "('yt:1', 'video', 'feed', 'inbox', 'A Talk', 'A Channel', 'https://video.example/1', ?)", (at(d, 9, 30),))
    rows = [("art:kk:1:" + d, "article", "daf-read", "kk:1", "How to Begin", "A Blog", at(d, 8, 0), 600, d, 0),
            ("kin:abc:" + d, "kindle", "kindle", "abc", "A Field Guide", "A. Writer", at(d, 6, 0), 1800, d, 0),
            ("kin:zzz:" + d, "kindle", "kindle", "zzz", "Step Work", "Someone", at(d, 7, 0), 900, d, 1)]
    c.executemany("INSERT INTO sessions (id, source, origin, item, title, author, start, seconds, day, private) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return c


class Recents(unittest.TestCase):
    def test_a_day(self):
        r = recents.days(conn(), SETTINGS, before="2026-03-05", n=3)
        self.assertEqual([d["date"] for d in r["days"]], ["2026-03-04"])
        items = r["days"][0]["items"]
        # newest first; the article once (its sitting and its later open are one row, with the sitting's minutes)
        self.assertEqual([x["title"] for x in items], ["How to Begin", "A Talk", "Private reading", "A Field Guide"])
        self.assertEqual(items[0]["minutes"], 10)
        self.assertEqual(items[0]["go"], "read/kk:1")
        self.assertEqual(items[0]["time"], "21:00")
        # a Kindle sitting opens its book, with the cover; a private one has no link or name
        self.assertEqual(items[3]["go"], "book/cal:1")
        self.assertEqual(items[3]["pic"], "/api/cover/cal:1")
        self.assertIsNone(items[2]["go"])
        self.assertIsNone(items[2]["author"])
        self.assertIsNone(r["next"])

    def test_paging(self):
        r = recents.days(conn(), SETTINGS, before="2026-03-10", n=3)
        self.assertEqual(r["days"], [])
        self.assertEqual(r["next"], "2026-03-07")


if __name__ == "__main__":
    unittest.main()
